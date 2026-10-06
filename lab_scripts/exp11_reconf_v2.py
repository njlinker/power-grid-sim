# -*- coding: utf-8 -*-
"""
实验十一：R004 v2（自动 tie_map + 故障隔离）验证
================================================
对比 R004 v1（硬编码 tie_map）和 v2（自动 tie_map + 故障隔离）

场景 A：S01 跳闸（下游 F1B 失电，v1 行为：仅合 TIE）
场景 B：S01 + S13 同时跳（更严重故障，v2 应先隔离 S13 故障段）

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp11_reconf_v2.py
"""

import warnings
warnings.filterwarnings("ignore")

from event_sim import Simulator, make_schedule
from rule_engine import build_reconfigure_rule, FaultTracker
from radial_feeder import (
    build_radial_feeder, LN_S01, LN_S13, LN_S02, LN_S24, LN_TIE,
    BUS_F1B, BUS_F2B,
)


def run_v1(scenario_name: str, schedule, duration: float):
    """v1：硬编码 tie_map，无故障隔离。"""
    grid = build_radial_feeder()
    sim = Simulator(grid, dt=1.0, verbose=False)
    rule = build_reconfigure_rule(
        tie_map={BUS_F1B: LN_TIE, BUS_F2B: LN_TIE},
        fault_isolation=False,
    )
    engine = type(rule) and __import__("rule_engine").RuleEngine([rule], name="v1")
    df = sim.run(duration, schedule, rules=engine)
    return df, engine


def run_v2(scenario_name: str, schedule, duration: float):
    """v2：自动 tie_map + 故障隔离。"""
    grid = build_radial_feeder()
    tracker = FaultTracker(window_s=20.0)
    sim = Simulator(grid, dt=1.0, verbose=False, fault_tracker=tracker)
    rule = build_reconfigure_rule(
        tie_map=None,
        auto_tie_map=True,
        fault_isolation=True,
        fault_tracker=tracker,
    )
    engine = type(rule) and __import__("rule_engine").RuleEngine([rule], name="v2")
    df = sim.run(duration, schedule, rules=engine)
    return df, engine


def report(label, df, engine):
    conv = df[df["converged"]]
    if len(conv) == 0:
        print(f"  {label}: PF 未收敛")
        return
    f1b_v = float(conv["v_F1B"].min()) if "v_F1B" in conv.columns else 0
    blackout = int((conv["v_F1B"] < 0.01).sum()) if "v_F1B" in conv.columns else -1
    line_cols = [c for c in conv.columns if c.startswith("line_")]
    max_load = float(conv[line_cols].max().max())
    print(f"  {label}: F1B_min={f1b_v:.4f} pu  blackout={blackout}  "
          f"max_load={max_load:.1f}%  fires={len(engine.log)}")
    for t, rid, msg in engine.log[:5]:
        print(f"    t={t:.1f} {rid}: {msg[:80]}")


def main():
    print("=" * 70)
    print("场景 A：S01 跳闸（F1B 失电）")
    print("=" * 70)
    sched_a = make_schedule(
        (5.0,  "line_trip", LN_S01),
        (30.0, "line_close", LN_S01),
        (30.0, "line_trip", LN_TIE),
    )
    df1, eng1 = run_v1("S01 trip", sched_a, 40.0)
    df2, eng2 = run_v2("S01 trip", sched_a, 40.0)
    print("\n--- R004 v1（硬编码，无隔离）---")
    report("v1", df1, eng1)
    print("\n--- R004 v2（自动 tie_map + 故障隔离）---")
    report("v2", df2, eng2)

    print("\n" + "=" * 70)
    print("场景 B：S01 + S13 同时跳（F1A/F1B 都失电，故障段需隔离）")
    print("=" * 70)
    sched_b = make_schedule(
        (5.0, "line_trip", LN_S01),
        (5.0, "line_trip", LN_S13),
    )
    df3, eng3 = run_v1("double trip", sched_b, 30.0)
    df4, eng4 = run_v2("double trip", sched_b, 30.0)
    print("\n--- R004 v1（硬编码，无隔离）---")
    report("v1", df3, eng3)
    print("\n--- R004 v2（自动 tie_map + 故障隔离）---")
    report("v2", df4, eng4)


if __name__ == "__main__":
    main()
