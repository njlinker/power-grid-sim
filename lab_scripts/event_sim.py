# -*- coding: utf-8 -*-
"""
事件驱动的电网仿真核心模块（Phase 1）
================================================
提供三件东西：
  1. Event        —— 描述一次扰动（何时、对谁、做什么）
  2. inject()     —— 把 Event 应用到 VeraGrid 的 grid 对象上
  3. Simulator    —— 主循环：基线 → 事件触发 → 重新潮流 → 状态快照

设计要点：
  - 用对象 .active = False / True 控制设备投退（VeraGrid 原生支持）
  - 不依赖 pf.loading（实测该字段对未通流支路返回垃圾值），自己用 Pf/rate 算
  - 不收敛时返回 NaN 状态而不是抛异常，便于上层做异常处理
  - 时间步长 dt 可以任意，连续事件/扰动都可以塞进 schedule

API 约定：
  - 所有名称以 grid 上的 .name 字符串为准（IEEE 14 的发电机是 '1_1'，母线是 'BUS 1'）
  - 事件时间 t 单位 = 仿真"秒"（你可以随便解读成什么，只要 dt 一致）
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd
import VeraGridEngine as vg

# 抑制 VeraGrid 的 RuntimeWarning
import warnings
warnings.filterwarnings("ignore")


# ============================================================ Event 数据结构
@dataclass(frozen=True)
class Event:
    """一次扰动的描述。

    kind  : 'load_add' / 'load_drop' / 'gen_trip' / 'gen_commit'
            'line_trip' / 'line_close'
    target: 目标对象的 name（按 grid.buses / generators / lines 上的 .name）
    t     : 触发时间（与 Simulator 的 dt 同单位）
    magnitude: 仅 load_add 用，单位 MW；缺省 0
    """
    t: float
    kind: str
    target: str
    magnitude: float = 0.0

    def __post_init__(self):
        valid = {"load_add", "load_drop", "gen_trip", "gen_commit",
                 "line_trip", "line_close"}
        if self.kind not in valid:
            raise ValueError(f"未知事件类型 {self.kind!r}，可选 {valid}")


def make_schedule(*specs) -> list[Event]:
    """便捷构造器：
        make_schedule((10, 'load_add', 'BUS 14', 50.0),
                      (30, 'gen_trip', '2_1'),
                      (60, 'line_trip', '2_4_1'))
    """
    return [Event(*s) for s in specs]


# ============================================================ 名称查找辅助
def find_bus(grid, name: str):
    for b in grid.buses:
        if b.name == name:
            return b
    raise KeyError(f"找不到母线 {name!r}")


def find_generator(grid, name: str):
    for gen in grid.get_generators():
        if gen.name == name:
            return gen
    raise KeyError(f"找不到发电机 {name!r}")


def find_line(grid, name: str):
    for ln in grid.lines:
        if ln.name == name:
            return ln
    raise KeyError(f"找不到线路 {name!r}")


def find_load(grid, name: str):
    for ld in grid.get_loads():
        if ld.name == name:
            return ld
    raise KeyError(f"找不到负荷 {name!r}")


# ============================================================ 事件注入
_load_counter = 0  # 给动态新增的负荷起名（全局计数器，跨调用递增）


def reset_load_counter():
    """把负荷计数器重置为 0。在跑新场景前调用，确保 load_add 命名从 _evt_1 开始。"""
    global _load_counter
    _load_counter = 0


def inject(grid, event: Event) -> str:
    """把事件应用到 grid 上，返回人类可读的描述。"""
    global _load_counter

    if event.kind == "load_add":
        bus = find_bus(grid, event.target)
        _load_counter += 1
        new_ld = vg.Load(
            name=f"_evt_{_load_counter}",
            P=float(event.magnitude),
            Q=float(event.magnitude * 0.3),  # 默认 0.3 功率因数
        )
        grid.add_load(bus, new_ld)
        return f"[t={event.t:6.1f}] +{event.magnitude:6.2f}MW @ {event.target}"

    if event.kind == "load_drop":
        ld = find_load(grid, event.target)
        if ld.active:
            ld.active = False
            msg = f"[t={event.t:6.1f}] -load {event.target} (P={ld.P:.2f}MW)"
        else:
            msg = f"[t={event.t:6.1f}] load_drop 跳过：{event.target} 已停机"
        return msg

    if event.kind == "gen_trip":
        gen = find_generator(grid, event.target)
        if gen.active:
            gen.active = False
            msg = f"[t={event.t:6.1f}] !! TRIP {event.target} (Pset={gen.P:.1f}MW)"
        else:
            msg = f"[t={event.t:6.1f}] gen_trip 跳过：{event.target} 已停机"
        return msg

    if event.kind == "gen_commit":
        gen = find_generator(grid, event.target)
        gen.active = True
        return f"[t={event.t:6.1f}] ++ COMMIT {event.target}"

    if event.kind == "line_trip":
        ln = find_line(grid, event.target)
        ln.active = False
        return f"[t={event.t:6.1f}] !! LINE TRIP {event.target}"

    if event.kind == "line_close":
        ln = find_line(grid, event.target)
        ln.active = True
        return f"[t={event.t:6.1f}] ++ LINE CLOSE {event.target}"

    raise ValueError(f"未实现的事件类型：{event.kind}")


# ============================================================ 状态快照
def snapshot(grid, pf, t: float) -> dict:
    """把潮流结果摊平成一个字典，便于组成 DataFrame。

    返回字段：
      - t           : 时间
      - converged   : bool
      - v_<bus>     : 各节点 |V|（pu）
      - line_<name> : 各线路 loading（% = |Pf|/rate × 100）
      - gen_<name>  : 各发电机有功出力（MW，从 pf.Sbus 推出）
      - loss_mw     : 总有功损耗
    """
    rec: dict = {"t": t, "converged": bool(pf.converged)}

    if not pf.converged:
        # 不收敛时所有数值字段填 NaN
        for b in grid.buses:
            rec[f"v_{b.name}"] = np.nan
        for ln in grid.lines:
            rec[f"line_{ln.name}"] = np.nan
            rec[f"sw_{ln.name}"] = np.nan  # 开关状态
        for gen in grid.get_generators():
            rec[f"gen_{gen.name}"] = np.nan
        rec["loss_mw"] = np.nan
        return rec

    # 节点电压
    for bus, v in zip(grid.buses, pf.voltage):
        rec[f"v_{bus.name}"] = float(abs(v))

    # 线路 loading（自己算，避开 pf.loading 的 bug）
    # Sf 是线路从端复功率（MW/Mvar），rate 是热稳定限额（MVA）
    # VeraGrid 默认 rate=1.0（对几乎所有线路都不合理），所以用 < 5.0 作为"未设置"判定
    for ln, sf in zip(grid.lines, pf.Sf):
        rate = float(getattr(ln, "rate", 0.0))
        if rate < 5.0:
            # 按电压等级默认：≥110kV 用 150MVA，35-110kV 用 50MVA，<35kV 用 20MVA
            vnom = max(ln.bus_from.Vnom, ln.bus_to.Vnom)
            if vnom >= 110:
                rate = 150.0
            elif vnom >= 35:
                rate = 50.0
            else:
                rate = 20.0
        rec[f"line_{ln.name}"] = float(abs(sf) / rate * 100.0)
        # 同步记录线路的"开关状态"（active=True=闭合）
        rec[f"sw_{ln.name}"] = int(bool(ln.active))

    # 发电机出力：从 Sbus（已经是 MW ！）反推
    # Sbus[i] = P_gen_at_bus - P_load_at_bus （净注入）
    # 所以 P_gen = Sbus[i].real + sum(local loads)
    Sbus = pf.Sbus
    bus_idx_of = {id(b): i for i, b in enumerate(grid.buses)}
    for gen in grid.get_generators():
        idx = bus_idx_of.get(id(gen.bus))
        local_load = sum(ld.P for ld in grid.get_loads()
                         if id(ld.bus) == id(gen.bus) and ld.active)
        if idx is not None:
            rec[f"gen_{gen.name}"] = float(Sbus[idx].real) + local_load
        else:
            rec[f"gen_{gen.name}"] = float(gen.P)

    # 总有功损耗 = sum(Sbus.real) —— 已是 MW
    rec["loss_mw"] = float(pf.Sbus.real.sum())

    return rec


# ============================================================ 仿真器
class Simulator:
    """事件驱动的准稳态仿真器。

    用法：
        sim = Simulator(grid, dt=1.0)
        schedule = make_schedule(
            (10, 'load_add', 'BUS 14', 50.0),
            (30, 'gen_trip', '2_1'),
        )
        df = sim.run(duration=120.0, schedule=schedule)

    返回的 df 是宽表：行为时间，列为状态量。
    """

    def __init__(self, grid, dt: float = 1.0,
                 solver=vg.SolverType.NR,
                 verbose: bool = False,
                 profiler=None,
                 fault_tracker=None):
        self.grid = grid
        self.dt = float(dt)
        self.opts = vg.PowerFlowOptions(solver_type=solver, verbose=0)
        self.verbose = verbose
        self.profiler = profiler  # LoadProfiler | None
        self.fault_tracker = fault_tracker  # FaultTracker | None

    def run(self, duration: float, schedule: list[Event] | None = None,
            on_event: Optional[Callable[[Event, str], None]] = None,
            rules=None,
            ) -> pd.DataFrame:
        """主循环：基线 → 步进 → 事件触发 → 潮流 → 规则评估 → 快照。

        Parameters
        ----------
        rules : RuleEngine | None
            可选的规则引擎。若提供，每步在 PF 后评估，触发的动作会修改 grid
            （效果在下一次 PF 中体现，即 1 步延迟，对秒级保护规则够用）
        profiler : LoadProfiler | None
            可选的负荷时序演化器。若提供，每步在 PF 前 tick（更新 ZIP/闪烁/启停），
            PF 后 update_v（记录母线电压供下一步 ZIP 用）
        """
        schedule = schedule or []
        # 按时间排序，便于在循环里判断触发
        schedule = sorted(schedule, key=lambda e: e.t)
        next_evt_idx = 0

        # 重置动态负荷计数器（保证本场景的 load_add 从 _evt_1 开始命名）
        reset_load_counter()

        records: list[dict] = []

        # 基线
        # 如果有 profiler，先 tick 一次让 load 状态到位
        if self.profiler is not None:
            self.profiler.tick(self.grid, t=0.0, dt=self.dt)
        pf = vg.power_flow(self.grid, options=self.opts)
        if self.profiler is not None:
            self.profiler.update_v({b.name: abs(v) for b, v in zip(self.grid.buses, pf.voltage)})
        records.append(snapshot(self.grid, pf, t=0.0))
        if self.verbose:
            print(f"[t=  0.0] 基线 converged={pf.converged}  "
                  f"loss={records[-1]['loss_mw']:.2f}MW")

        t = 0.0
        n_steps = int(round(duration / self.dt))
        for step in range(1, n_steps + 1):
            t = step * self.dt

            # 0. 负荷时序演化（ZIP/闪烁/启停）
            if self.profiler is not None:
                self.profiler.tick(self.grid, t=t, dt=self.dt)

            # 1. 处理所有 ≤ 当前时间的未触发事件
            while next_evt_idx < len(schedule) and schedule[next_evt_idx].t <= t:
                ev = schedule[next_evt_idx]
                msg = inject(self.grid, ev)
                # 记录线路故障给 FaultTracker
                if self.fault_tracker is not None and ev.kind == "line_trip":
                    self.fault_tracker.record(ev.target, t)
                if self.verbose:
                    print(msg)
                if on_event is not None:
                    on_event(ev, msg)
                next_evt_idx += 1

            # 2. 重新潮流
            pf = vg.power_flow(self.grid, options=self.opts)
            rec = snapshot(self.grid, pf, t=t)
            rec["rules_fired"] = ""

            # 3. 把电压回传给 profiler（供下一步 ZIP 用）
            if self.profiler is not None:
                self.profiler.update_v(
                    {b.name: abs(v) for b, v in zip(self.grid.buses, pf.voltage)}
                )

            # 4. 规则评估：动作会修改 grid，重跑一次 PF 让动作立即生效
            #    （否则规则动作要等下一帧才可见，导致 1 步延迟）
            if rules is not None:
                fired = rules.evaluate(self.grid, rec, t)
                if fired:
                    rec["rules_fired"] = ",".join(r.id for r in fired)
                    if self.verbose:
                        for r in fired:
                            last_log = rules.log[-1]
                            print(f"  >> RULE {r.id}: {last_log[2]}")
                    # 重跑 PF + 重新 snapshot，让动作立即可见
                    pf = vg.power_flow(self.grid, options=self.opts)
                    rec = snapshot(self.grid, pf, t=t)
                    rec["rules_fired"] = ",".join(r.id for r in fired)
                    # 更新 profiler 电压
                    if self.profiler is not None:
                        self.profiler.update_v(
                            {b.name: abs(v) for b, v in zip(self.grid.buses, pf.voltage)}
                        )

            records.append(rec)
            if self.verbose and step % max(1, n_steps // 20) == 0:
                pct = 100 * step / n_steps
                cv = "OK" if pf.converged else "FAIL"
                print(f"[t={t:6.1f}] step {step:4d}/{n_steps} ({pct:5.1f}%)  {cv}")

        return pd.DataFrame(records)


# ============================================================ 便捷分析函数
def summarize_events(df: pd.DataFrame, bus_names: list[str] | None = None,
                     line_names: list[str] | None = None) -> pd.DataFrame:
    """从状态 DataFrame 提取关键事件时刻的快照。"""
    rows = []
    # 取有事件发生的时刻
    interesting = df[df["converged"]].copy()
    for t in interesting["t"].unique():
        snap = interesting[interesting["t"] == t].iloc[0]
        row = {"t": t}
        if bus_names:
            for b in bus_names:
                key = f"v_{b}"
                if key in snap:
                    row[f"v_{b}"] = snap[key]
        if line_names:
            for ln in line_names:
                key = f"line_{ln}"
                if key in snap:
                    row[f"line_{ln}"] = snap[key]
        row["loss_mw"] = snap.get("loss_mw", np.nan)
        rows.append(row)
    return pd.DataFrame(rows)
