# -*- coding: utf-8 -*-
"""
规则生成器（Phase 4）
================================================
从"规则模板空间"枚举候选规则，在仿真场景里评估打分，输出 top-N 规则。

核心抽象：
  RuleSpec      候选规则的"配方"（条件 + 动作 + 参数）
  materialize   把 RuleSpec 实例化为可执行的 Rule
  evaluate      在指定场景下跑仿真，返回 (score, metrics)
  run_search    并行/串行评估一组 RuleSpec，按 score 排名

适用场景：
  - 已确定拓扑（如辐射状 feeder）和典型事件剧本
  - 想从大量候选规则中筛选最优（而不靠人工事先调参）
  - 想对比"哪条规则在哪个场景下最有效"

候选生成模板：
  - UVLS   (V < threshold) -> shed fraction at bus
  - OVGR   (V > threshold) -> reduce gen fraction at bus
  - OVERLOAD (line_loading > threshold%) -> shed at receiving bus
  - RECONF (blackout) -> close tie switch
  - RECONF_LINE (line_trip event) -> open sectionalizer + close tie
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np
import pandas as pd

import VeraGridEngine as vg
from event_sim import Simulator, Event, make_schedule
from rule_engine import Rule, RuleEngine, _is_nan

import warnings
warnings.filterwarnings("ignore")


# ============================================================ RuleSpec
@dataclass
class RuleSpec:
    """候选规则配方。

    Attributes
    ----------
    name : str
    family : str
        'UVLS' | 'OVGR' | 'OVERLOAD' | 'RECONF'
    threshold : float
        条件阈值（pu 电压 / 百分比载流）
    target : str
        动作目标（母线名 / 开关名 / 发电机名）
    action_param : float
        动作强度（切负荷比例 / 降出力比例）
    cooldown_s : float
    """
    name: str
    family: str
    threshold: float
    target: str
    action_param: float
    cooldown_s: float = 5.0
    description: str = ""

    def __post_init__(self):
        if not self.description:
            self.description = self._auto_desc()

    def _auto_desc(self) -> str:
        if self.family == "UVLS":
            return f"IF V<{self.threshold} THEN shed {self.action_param*100:.0f}% on {self.target}"
        if self.family == "OVGR":
            return f"IF V>{self.threshold} THEN reduce gen {self.action_param*100:.0f}% on {self.target}"
        if self.family == "OVERLOAD":
            return f"IF loading>{self.threshold}% THEN shed {self.action_param*100:.0f}% on {self.target}"
        if self.family == "RECONF":
            return f"IF blackout THEN close switch {self.target}"
        return f"{self.family}({self.threshold},{self.target},{self.action_param})"


# ============================================================ materialize
def materialize(spec: RuleSpec) -> Rule:
    """把 RuleSpec 转为可执行 Rule。"""
    if spec.family == "UVLS":
        return _uvls_rule(spec)
    if spec.family == "OVGR":
        return _ovgr_rule(spec)
    if spec.family == "OVERLOAD":
        return _overload_rule(spec)
    if spec.family == "RECONF":
        return _reconf_rule(spec)
    raise ValueError(f"未知 family: {spec.family}")


def _uvls_rule(spec: RuleSpec) -> Rule:
    def when(state, grid):
        for key, val in state.items():
            if key.startswith("v_") and isinstance(val, (int, float)) and not _is_nan(val):
                if val < spec.threshold:
                    return True
        return False

    def then(grid, state):
        worst_bus, worst_v = None, 1e9
        for key, val in state.items():
            if key.startswith("v_") and isinstance(val, (int, float)) and not _is_nan(val):
                if val < worst_v:
                    worst_v = val
                    worst_bus = key[2:]
        if worst_bus is None:
            return "no bus"
        # 切目标母线（或最差母线）的负荷
        target_bus = spec.target if spec.target != "*" else worst_bus
        loads = [ld for ld in grid.get_loads()
                 if ld.bus.name == target_bus and ld.active]
        if not loads:
            return f"no active load on {target_bus}"
        ld = max(loads, key=lambda x: x.P)
        shed = ld.P * spec.action_param
        ld.P -= shed
        if ld.P < 1e-3:
            ld.active = False
        return f"shed {shed:.2f}MW on {target_bus} (V_min={worst_v:.3f})"

    return Rule(id=spec.name, description=spec.description,
                when=when, then=then, cooldown_s=spec.cooldown_s)


def _ovgr_rule(spec: RuleSpec) -> Rule:
    def when(state, grid):
        slack = {b.name for b in grid.buses if getattr(b, 'is_slack', False)}
        for key, val in state.items():
            if key.startswith("v_") and isinstance(val, (int, float)) and not _is_nan(val):
                if key[2:] not in slack and val > spec.threshold:
                    return True
        return False

    def then(grid, state):
        slack = {b.name for b in grid.buses if getattr(b, 'is_slack', False)}
        worst_bus, worst_v = None, -1e9
        for key, val in state.items():
            if key.startswith("v_") and isinstance(val, (int, float)) and not _is_nan(val):
                if key[2:] not in slack and val > worst_v:
                    worst_v = val
                    worst_bus = key[2:]
        if worst_bus is None:
            return "no overvoltage"
        gens = [g for g in grid.get_generators()
                if g.bus.name == worst_bus and g.active and g.P > 1e-3]
        if not gens:
            gens = [g for g in grid.get_generators() if g.active and g.P > 1e-3]
        if not gens:
            return "no active gen"
        g = max(gens, key=lambda x: x.P)
        delta = g.P * spec.action_param
        g.P -= delta
        return f"reduce {g.name} by {delta:.2f}MW (V_max={worst_v:.3f})"

    return Rule(id=spec.name, description=spec.description,
                when=when, then=then, cooldown_s=spec.cooldown_s)


def _overload_rule(spec: RuleSpec) -> Rule:
    def when(state, grid):
        for key, val in state.items():
            if key.startswith("line_") and isinstance(val, (int, float)) and not _is_nan(val):
                if val > spec.threshold:
                    return True
        return False

    def then(grid, state):
        worst_line, worst_load = None, -1e9
        for key, val in state.items():
            if key.startswith("line_") and isinstance(val, (int, float)) and not _is_nan(val):
                if val > worst_load:
                    worst_load = val
                    worst_line = key[5:]
        if worst_line is None:
            return "no overload"
        target_line = next((ln for ln in grid.lines if ln.name == worst_line), None)
        if target_line is None:
            return f"line {worst_line} not found"
        target_bus = spec.target if spec.target != "*" else target_line.bus_to.name
        loads = [ld for ld in grid.get_loads()
                 if ld.bus.name == target_bus and ld.active]
        if not loads:
            return f"no load on {target_bus}"
        ld = max(loads, key=lambda x: x.P)
        shed = ld.P * spec.action_param
        ld.P -= shed
        if ld.P < 1e-3:
            ld.active = False
        return f"shed {shed:.2f}MW on {target_bus} (line={worst_line}={worst_load:.1f}%)"

    return Rule(id=spec.name, description=spec.description,
                when=when, then=then, cooldown_s=spec.cooldown_s)


def _reconf_rule(spec: RuleSpec) -> Rule:
    """检测失电母线 -> 闭合指定 tie 开关"""
    def when(state, grid):
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
        target = next((ln for ln in grid.lines if ln.name == spec.target), None)
        if target is None:
            return f"switch {spec.target} not found"
        if target.active:
            return f"{spec.target} already closed"
        target.active = True
        return f"close {spec.target} to restore blackout"

    return Rule(id=spec.name, description=spec.description,
                when=when, then=then, cooldown_s=spec.cooldown_s)


# ============================================================ 候选生成器
def gen_uvls_candidates(v_thresholds=(0.90, 0.92, 0.94, 0.96),
                        shed_fractions=(0.1, 0.2, 0.3, 0.5),
                        targets=("*",)) -> list[RuleSpec]:
    """UVLS 候选：V < v_thresh -> 在 target 母线切 shed_fraction。target="*" 表示"最差母线"。"""
    out = []
    for v in v_thresholds:
        for f in shed_fractions:
            for t in targets:
                t_short = "WORST" if t == "*" else t
                name = f"UVLS_v{int(v*100)}_f{int(f*100)}_{t_short}"
                out.append(RuleSpec(name=name, family="UVLS",
                                    threshold=v, target=t, action_param=f))
    return out


def gen_overload_candidates(load_thresholds=(110.0, 130.0, 150.0, 170.0),
                            shed_fractions=(0.05, 0.10, 0.20),
                            targets=("*",)) -> list[RuleSpec]:
    out = []
    for lt in load_thresholds:
        for f in shed_fractions:
            for t in targets:
                t_short = "WORST" if t == "*" else t
                name = f"OVL_lt{int(lt)}_f{int(f*100)}_{t_short}"
                out.append(RuleSpec(name=name, family="OVERLOAD",
                                    threshold=lt, target=t, action_param=f))
    return out


def gen_reconf_candidates(tie_switches=("TIE",)) -> list[RuleSpec]:
    out = []
    for tie in tie_switches:
        name = f"RECONF_{tie}"
        out.append(RuleSpec(name=name, family="RECONF",
                            threshold=0.05, target=tie, action_param=0.0))
    return out


# ============================================================ 评估
@dataclass
class Scenario:
    """仿真场景定义。"""
    name: str
    duration: float
    schedule: list[Event]
    grid_factory: Callable  # () -> MultiCircuit


def evaluate_rule(spec: RuleSpec, scenario: Scenario,
                  key_v_bus: str = "F1B") -> tuple[float, dict]:
    """跑一次仿真，返回 (score, metrics_dict)。

    评分（越高越好）：
      + 100 × 最低电压（pu）
      - 0.1 × 最大载流（%）
      - 2.0 × 失电步数
      - 0.01 × 最大损耗（MW）
      - 0.05 × 切负荷量（MW）
    """
    grid = scenario.grid_factory()
    base_load = sum(ld.P for ld in grid.get_loads() if ld.active)

    sim = Simulator(grid, dt=1.0, verbose=False)
    rule = materialize(spec)
    engine = RuleEngine([rule], name=spec.name)
    df = sim.run(scenario.duration, scenario.schedule, rules=engine)

    conv = df[df["converged"]]
    n_total = len(df)
    n_conv = len(conv)

    if n_conv == 0:
        return -1e9, {"n_conv": 0, "n_total": n_total}

    v_cols = [c for c in conv.columns if c.startswith("v_")]
    line_cols = [c for c in conv.columns if c.startswith("line_")]

    min_v = float(conv[v_cols].min().min())
    max_load = float(conv[line_cols].max().max())
    max_loss = float(conv["loss_mw"].max())

    # 关键母线失电时长（默认 F1B，可改）—— 用更严格的阈值 V<0.01
    blackout_steps = int((conv[f"v_{key_v_bus}"] < 0.01).sum()) \
        if f"v_{key_v_bus}" in conv.columns else 0

    # 切负荷量
    final_load = sum(ld.P for ld in grid.get_loads() if ld.active)
    shed = max(base_load - final_load, 0)

    score = (100 * min_v
             - 0.1 * max_load
             - 2.0 * blackout_steps
             - 0.01 * max_loss
             - 0.05 * shed)

    metrics = {
        "n_conv": n_conv, "n_total": n_total,
        "min_v": min_v, "max_load": max_load, "max_loss": max_loss,
        "blackout_steps": blackout_steps, "shed_mw": shed,
        "fire_count": rule.fire_count,
    }
    return score, metrics


def evaluate_compound(specs: list[RuleSpec], scenario: Scenario,
                      compound_name: str = "compound",
                      key_v_bus: str = "F1B") -> tuple[float, dict]:
    """评估一组规则同时启用的情况。"""
    grid = scenario.grid_factory()
    base_load = sum(ld.P for ld in grid.get_loads() if ld.active)

    sim = Simulator(grid, dt=1.0, verbose=False)
    rules = [materialize(s) for s in specs]
    engine = RuleEngine(rules, name=compound_name)
    df = sim.run(scenario.duration, scenario.schedule, rules=engine)

    conv = df[df["converged"]]
    if len(conv) == 0:
        return -1e9, {"n_conv": 0}

    v_cols = [c for c in conv.columns if c.startswith("v_")]
    line_cols = [c for c in conv.columns if c.startswith("line_")]
    min_v = float(conv[v_cols].min().min())
    max_load = float(conv[line_cols].max().max())
    max_loss = float(conv["loss_mw"].max())
    blackout_steps = int((conv[f"v_{key_v_bus}"] < 0.01).sum()) \
        if f"v_{key_v_bus}" in conv.columns else 0
    final_load = sum(ld.P for ld in grid.get_loads() if ld.active)
    shed = max(base_load - final_load, 0)

    score = (100 * min_v
             - 0.1 * max_load
             - 2.0 * blackout_steps
             - 0.01 * max_loss
             - 0.05 * shed)

    fire_counts = ", ".join(f"{r.id}:{r.fire_count}" for r in rules)
    return score, {
        "n_conv": len(conv), "n_total": len(df),
        "min_v": min_v, "max_load": max_load, "max_loss": max_loss,
        "blackout_steps": blackout_steps, "shed_mw": shed,
        "fire_count": fire_counts,
    }


def run_search(scenario: Scenario, specs: list[RuleSpec],
               baseline_grid_factory: Optional[Callable] = None,
               top_n: int = 10,
               verbose: bool = True) -> pd.DataFrame:
    """评估所有候选规则，按 score 降序排名，返回 DataFrame。"""
    # 先跑 baseline（无规则）作为参考
    if baseline_grid_factory is not None:
        grid = baseline_grid_factory()
        sim = Simulator(grid, dt=1.0, verbose=False)
        df = sim.run(scenario.duration, scenario.schedule, rules=None)
        conv = df[df["converged"]]
        if len(conv) > 0:
            v_cols = [c for c in conv.columns if c.startswith("v_")]
            line_cols = [c for c in conv.columns if c.startswith("line_")]
            baseline_metrics = {
                "min_v": float(conv[v_cols].min().min()),
                "max_load": float(conv[line_cols].max().max()),
                "max_loss": float(conv["loss_mw"].max()),
                "blackout_steps": int((conv.get("v_F1B", pd.Series([1.0])) < 0.05).sum())
                                  if "v_F1B" in conv.columns else 0,
            }
        else:
            baseline_metrics = {"min_v": 0, "max_load": 999, "max_loss": 999, "blackout_steps": 999}
    else:
        baseline_metrics = {}

    rows = []
    for i, spec in enumerate(specs):
        score, m = evaluate_rule(spec, scenario)
        rows.append({
            "rank": 0,
            "family": spec.family,
            "name": spec.name,
            "description": spec.description,
            "threshold": spec.threshold,
            "target": spec.target,
            "action_param": spec.action_param,
            "score": score,
            **m,
        })
        if verbose and (i + 1) % 10 == 0:
            print(f"  评估进度 {i+1}/{len(specs)}: best so far {max(r['score'] for r in rows):.2f}")

    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    if verbose:
        print(f"\n评估完成: {len(specs)} 条规则")
        if baseline_metrics:
            print(f"  baseline (无规则): "
                  f"min_v={baseline_metrics.get('min_v', 0):.4f} "
                  f"max_load={baseline_metrics.get('max_load', 0):.1f}% "
                  f"blackout={baseline_metrics.get('blackout_steps', 0)}")
        print(f"  top score: {df.iloc[0]['score']:.2f} ({df.iloc[0]['name']})")
        print(f"\nTop {top_n}:")
        cols = ["rank", "family", "score", "min_v", "max_load", "blackout_steps",
                "fire_count", "description"]
        print(df[cols].head(top_n).to_string(index=False))

    return df, baseline_metrics
