# -*- coding: utf-8 -*-
"""
规则引擎（Phase 3）
================================================
核心抽象：
  - Rule     : 一条 IF-THEN 规则
      · when(state, grid) -> bool   触发条件（纯函数，便于测试）
      · then(grid, state) -> str    动作（修改 grid，返回执行描述）
      · cooldown_s                  两次触发最小间隔，避免抖动

  - RuleEngine: 规则调度器
      · evaluate(grid, state, t) -> list[Rule]
      · 内部维护 last_fired_t，处理冷却

设计要点：
  - state 是上一时刻的快照字典（与 Simulator.snapshot 输出同构）
  - 规则动作直接修改 grid（set obj.active=False 等），与 Event 注入共用一套底层机制
  - 冷却期防止"低电压 → 切负荷 → 电压恢复 → 规则又触发切更多"的循环
  - 不依赖开关（Phase 2 之前的 v1），动作以"切负荷/调出力"为主
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import VeraGridEngine as vg

import warnings
warnings.filterwarnings("ignore")


# ============================================================ Rule 数据结构
@dataclass
class Rule:
    """一条 IF-THEN 规则。

    Attributes
    ----------
    id : str          唯一标识，写入日志
    description : str 人类可读描述
    when : Callable   触发条件，输入 (state_dict, grid) 返回 bool
    then : Callable   动作，输入 (grid, state_dict) 返回 str 描述
    cooldown_s : float  冷却期（秒）；0 表示无冷却
    persistent : bool    True=每次条件满足都触发（受冷却约束）
                       False=触发一次后该规则"沉默"，需要外部重置
    last_fired_t : float 上次触发时间
    fire_count : int     累计触发次数
    """
    id: str
    description: str
    when: Callable[[dict, object], bool]
    then: Callable[[object, dict], str]
    cooldown_s: float = 0.0
    persistent: bool = True
    last_fired_t: float = -1e9
    fire_count: int = 0
    enabled: bool = True


# ============================================================ RuleEngine
class RuleEngine:
    """规则调度器。每步评估一次，返回触发的规则列表。"""

    def __init__(self, rules: list[Rule], name: str = "engine"):
        self.rules = list(rules)
        self.name = name
        self.log: list[tuple[float, str, str]] = []  # (t, rule_id, msg)

    def evaluate(self, grid, state: dict, t: float) -> list[Rule]:
        """评估所有启用的规则，对触发的执行动作。"""
        fired: list[Rule] = []
        for rule in self.rules:
            if not rule.enabled:
                continue
            if not rule.persistent and rule.fire_count > 0:
                continue
            if (t - rule.last_fired_t) < rule.cooldown_s:
                continue
            try:
                ok = bool(rule.when(state, grid))
            except Exception as e:
                ok = False
                self.log.append((t, rule.id, f"ERROR in when(): {e}"))
                continue
            if ok:
                try:
                    msg = rule.then(grid, state)
                except Exception as e:
                    msg = f"ERROR in then(): {e}"
                rule.last_fired_t = t
                rule.fire_count += 1
                self.log.append((t, rule.id, msg))
                fired.append(rule)
        return fired

    def reset(self):
        """重置所有规则的触发状态（用于多次跑同一剧本）。"""
        for r in self.rules:
            r.last_fired_t = -1e9
            r.fire_count = 0
        self.log.clear()


# ============================================================ 工具函数
def get_v(state: dict, bus_name: str) -> float | None:
    """从 state 字典取某母线电压。"""
    return state.get(f"v_{bus_name}")


def get_line_loading(state: dict, line_name: str) -> float | None:
    return state.get(f"line_{line_name}")


def find_loads_on_bus(grid, bus_name: str) -> list:
    return [ld for ld in grid.get_loads() if ld.bus.name == bus_name and ld.active]


def find_generators_on_bus(grid, bus_name: str) -> list:
    return [gen for gen in grid.get_generators()
            if gen.bus.name == bus_name and gen.active]


def shed_load_fraction(grid, bus_name: str, fraction: float) -> str:
    """在指定母线上按比例切负荷。返回执行描述。"""
    loads = find_loads_on_bus(grid, bus_name)
    if not loads:
        return f"no active load on {bus_name}, no-op"
    # 选最大负荷切
    target = max(loads, key=lambda ld: ld.P)
    shed = target.P * fraction
    target.P -= shed
    if target.P < 1e-3:
        target.active = False
        return f"shed all {shed:.2f}MW on {bus_name} (load {target.name} removed)"
    return f"shed {shed:.2f}MW on {bus_name} (load {target.name} now P={target.P:.2f}MW)"


def reduce_gen_fraction(grid, bus_name: str, fraction: float) -> str:
    """在指定母线或最近母线上按比例降低发电机出力。
    跳过 P=0 的发电机（sync condenser 之类），找最近的有功发电机。
    """
    # 先在该母线找有功发电机
    gens = [g for g in find_generators_on_bus(grid, bus_name) if g.P > 1e-3]
    if not gens:
        # 退而求其次：找任意有功发电机
        gens = [g for g in grid.get_generators() if g.active and g.P > 1e-3]
        if not gens:
            return "no active generator with P>0, no-op"
    target = max(gens, key=lambda g: g.P)
    delta = target.P * fraction
    target.P -= delta
    if target.P < 0:
        target.P = 0.0
    return (f"reduce {target.name} by {delta:.2f}MW ({fraction*100:.0f}%) "
            f"-> Pset={target.P:.2f}MW")


# ============================================================ 三条基础规则
def build_default_rules(v_under: float = 0.93,
                        v_over: float = 1.10,
                        line_overload_pct: float = 130.0,
                        shed_fraction_uv: float = 0.30,
                        shed_fraction_overload: float = 0.10,
                        gen_reduce_fraction: float = 0.20,
                        cooldown: float = 5.0) -> list[Rule]:
    """构造一组默认规则：

    R001_UVLS      低压减载：任一节点 V < v_under pu 且持续 → 切该节点 30% 负荷
    R002_OVGR      过压减出力：任一节点 V > v_over pu → 降出力 20%
    R003_OVERLOAD  重载切负荷：任一线路 loading > line_overload_pct →
                  在该线路"to"端切 10% 负荷
    """

    def when_uvls(state, grid):
        # 任一节点低于阈值
        for key, val in state.items():
            if key.startswith("v_") and isinstance(val, (int, float)) and not _is_nan(val):
                if val < v_under:
                    return True
        return False

    def then_uvls(grid, state):
        # 找电压最低的母线，切其负荷
        worst_bus, worst_v = None, 1e9
        for key, val in state.items():
            if key.startswith("v_") and isinstance(val, (int, float)) and not _is_nan(val):
                if val < worst_v:
                    worst_v = val
                    worst_bus = key[2:]  # strip "v_"
        if worst_bus is None:
            return "no bus identified"
        msg = shed_load_fraction(grid, worst_bus, shed_fraction_uv)
        return f"[V={worst_v:.4f}<{v_under}] {msg}"

    def when_ovgr(state, grid):
        # 跳过 slack 母线（slack 的 V 是被 PV 控制钉住的，不该减出力）
        slack_buses = {b.name for b in grid.buses if getattr(b, 'is_slack', False)}
        for key, val in state.items():
            if key.startswith("v_") and isinstance(val, (int, float)) and not _is_nan(val):
                bus_name = key[2:]
                if bus_name in slack_buses:
                    continue
                if val > v_over:
                    return True
        return False

    def then_ovgr(grid, state):
        # 找电压最高的非 slack 母线
        slack_buses = {b.name for b in grid.buses if getattr(b, 'is_slack', False)}
        worst_bus, worst_v = None, -1e9
        for key, val in state.items():
            if key.startswith("v_") and isinstance(val, (int, float)) and not _is_nan(val):
                bus_name = key[2:]
                if bus_name in slack_buses:
                    continue
                if val > worst_v:
                    worst_v = val
                    worst_bus = bus_name
        if worst_bus is None:
            return "no non-slack bus above threshold, no-op"
        msg = reduce_gen_fraction(grid, worst_bus, gen_reduce_fraction)
        return f"[V={worst_v:.4f}>{v_over}] {msg}"

    def when_overload(state, grid):
        for key, val in state.items():
            if key.startswith("line_") and isinstance(val, (int, float)) and not _is_nan(val):
                if val > line_overload_pct:
                    return True
        return False

    def then_overload(grid, state):
        # 找最严重的线路
        worst_line, worst_load = None, -1e9
        for key, val in state.items():
            if key.startswith("line_") and isinstance(val, (int, float)) and not _is_nan(val):
                if val > worst_load:
                    worst_load = val
                    worst_line = key[5:]
        if worst_line is None:
            return "no line identified"
        # 找线路对象，取其 to 端母线
        target_line = None
        for ln in grid.lines:
            if ln.name == worst_line:
                target_line = ln
                break
        if target_line is None:
            return f"line {worst_line} not found"
        to_bus = target_line.bus_to.name
        msg = shed_load_fraction(grid, to_bus, shed_fraction_overload)
        return f"[line {worst_line}={worst_load:.1f}%>{line_overload_pct}] {msg}"

    rules = [
        Rule(
            id="R001_UVLS",
            description=f"低压减载：V<{v_under}pu -> 切30%负荷",
            when=when_uvls, then=then_uvls,
            cooldown_s=cooldown,
        ),
        Rule(
            id="R002_OVGR",
            description=f"过压减出力：V>{v_over}pu -> 降出力{gen_reduce_fraction*100:.0f}%",
            when=when_ovgr, then=then_ovgr,
            cooldown_s=cooldown,
        ),
        Rule(
            id="R003_OVERLOAD",
            description=f"重载切负荷：loading>{line_overload_pct}% -> 末端切{shed_fraction_overload*100:.0f}%",
            when=when_overload, then=then_overload,
            cooldown_s=cooldown,
        ),
    ]
    return rules


def build_reconfigure_rule(tie_map: dict[str, str] | None = None,
                           cooldown: float = 1.0) -> Rule:
    """R004_RECONFIGURE：检测失电母线并闭合对应的 tie 开关。

    Parameters
    ----------
    tie_map : dict
        映射 {失电母线名: 应闭合的 tie 开关名}，例如 {"F1B": "TIE", "F2B": "TIE"}
        若不提供，使用默认映射（F1B↔TIE, F2B↔TIE）
    cooldown : float
        重构规则冷却时间（秒）。一般设短一点（如 1s）以便快速恢复
    """
    if tie_map is None:
        tie_map = {"F1B": "TIE", "F2B": "TIE"}

    def when(state, grid):
        # 任一带载母线 V < 0.05 pu 视为失电
        for ld in grid.get_loads():
            if not ld.active:
                continue
            v = state.get(f"v_{ld.bus.name}")
            if v is None or _is_nan(v):
                continue
            if abs(v) < 0.05:
                return True
        return False

    def then(grid, state):
        actions = []
        for ld in grid.get_loads():
            if not ld.active:
                continue
            v = state.get(f"v_{ld.bus.name}")
            if v is None or _is_nan(v) or abs(v) >= 0.05:
                continue
            tie_name = tie_map.get(ld.bus.name)
            if not tie_name:
                continue
            # 找 tie 开关（用 Line.active 表示）
            tie = None
            for ln in grid.lines:
                if ln.name == tie_name:
                    tie = ln
                    break
            if tie is None or tie.active:
                continue
            tie.active = True
            actions.append(f"close {tie_name} to restore {ld.bus.name}")
        if not actions:
            return "blackout detected but no available tie"
        return "; ".join(actions)

    return Rule(
        id="R004_RECONFIGURE",
        description="自动重构：失电母线 -> 闭合对应 tie 开关",
        when=when, then=then,
        cooldown_s=cooldown,
    )


def _is_nan(x) -> bool:
    try:
        return x != x  # NaN != NaN
    except Exception:
        return False
