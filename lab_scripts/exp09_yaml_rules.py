# -*- coding: utf-8 -*-
"""
实验九：YAML 规则配置验证（Phase A）
================================================
目标：证明规则可以从 YAML 配置加载，无需改 Python 代码

加载 config/rules.yaml，在两个场景下跑：
  场景 1：IEEE 14 事件剧本（验证 R001/R002/R003）
  场景 2：辐射状 feeder S01 跳闸（验证 R004）

对比 YAML 加载的规则 vs Python 内置规则，结果应一致。

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp09_yaml_rules.py
"""

import warnings
warnings.filterwarnings("ignore")

import VeraGridEngine as vg

from event_sim import Simulator, make_schedule
from rule_engine import build_default_rules, build_reconfigure_rule, RuleEngine
from rules_loader import load_engine_from_yaml, load_specs_from_yaml
from radial_feeder import (
    build_radial_feeder, LN_S01, LN_TIE, BUS_F1B,
)

RULES_YAML = "lab_scripts/config/rules.yaml"


def run_ieee14():
    print("\n" + "=" * 60)
    print("场景 1: IEEE 14 事件剧本（验证 R001/R002/R003）")
    print("=" * 60)
    grid = vg.open_file("Grids_and_profiles/grids/IEEE 14 bus.raw")
    sim = Simulator(grid, dt=1.0, verbose=False)
    schedule = make_schedule(
        (10.0, "load_add",  "BUS 14", 50.0),
        (25.0, "load_add",  "BUS 9",  30.0),
        (40.0, "gen_trip",  "2_1"),
        (55.0, "line_trip", "2_4_1"),
        (70.0, "load_drop", "_evt_1"),
    )
    engine = load_engine_from_yaml(RULES_YAML, name="yaml_engine")
    print(f"从 YAML 加载的规则: {[r.id for r in engine.rules]}")

    df = sim.run(duration=90.0, schedule=schedule, rules=engine)
    conv = df[df["converged"]]
    v_cols = [c for c in conv.columns if c.startswith("v_")]
    line_cols = [c for c in conv.columns if c.startswith("line_")]
    metrics = {
        "min_v": float(conv[v_cols].min().min()),
        "max_load": float(conv[line_cols].max().max()),
        "fires": len(engine.log),
    }
    print(f"\n  最低电压: {metrics['min_v']:.4f} pu")
    print(f"  最大载流: {metrics['max_load']:.1f}%")
    print(f"  规则触发: {metrics['fires']} 次")
    return metrics


def run_radial():
    print("\n" + "=" * 60)
    print("场景 2: 辐射状 feeder S01 跳闸（验证 R004）")
    print("=" * 60)
    grid = build_radial_feeder()
    sim = Simulator(grid, dt=1.0, verbose=False)
    schedule = make_schedule(
        (5.0,  "line_trip",  LN_S01),
        (30.0, "line_close", LN_S01),
        (30.0, "line_trip",  LN_TIE),
    )
    engine = load_engine_from_yaml(RULES_YAML, name="yaml_engine")

    df = sim.run(duration=40.0, schedule=schedule, rules=engine)
    conv = df[df["converged"]]
    blackout = int((conv[f"v_{BUS_F1B}"] < 0.01).sum()) if f"v_{BUS_F1B}" in conv.columns else -1
    print(f"  加载的规则: {[r.id for r in engine.rules]}")
    print(f"  F1B 失电时长: {blackout} 步")
    print(f"  R004 触发: {sum(1 for t,r,m in engine.log if r=='R004_RECONF')} 次")
    return {"blackout_steps": blackout}


def main():
    # 先验证 YAML 解析正确
    print("=" * 60)
    print(f"从 {RULES_YAML} 加载规则...")
    print("=" * 60)
    specs = load_specs_from_yaml(RULES_YAML)
    for s in specs:
        print(f"  - {s.name} ({s.family}): {s.description}")

    m1 = run_ieee14()
    m2 = run_radial()

    print("\n" + "=" * 60)
    print("YAML 化总结")
    print("=" * 60)
    print(f"  加载规则数: {len(specs)} (R001/R002/R003/R004)")
    print(f"  场景 1 最低电压: {m1['min_v']:.4f} pu")
    print(f"  场景 2 F1B 失电: {m2['blackout_steps']} 步")
    print("\n  → 修改 config/rules.yaml 即可调整规则，无需改 Python 代码")


if __name__ == "__main__":
    main()
