# -*- coding: utf-8 -*-
"""
实验十：基准测试套件（Phase B 验证）
================================================
目标：自动跑现有规则集（从 YAML 加载）vs 场景库，输出通过率表

流程：
  1. 加载 config/rules.yaml
  2. 遍历 scenarios.py 中的所有场景
  3. 每个场景跑仿真，记录指标和 pass/fail
  4. 输出汇总表 + 详细失败分析 + 可视化

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp10_benchmark.py
"""

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

for cand in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS"):
    if any(cand in f.name for f in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [cand]
        break
plt.rcParams["axes.unicode_minus"] = False

from event_sim import Simulator
from rules_loader import load_engine_from_yaml
from scenarios import SCENARIOS, Scenario, PassCriteria


RULES_YAML = "lab_scripts/config/rules.yaml"


def evaluate_scenario(scenario: Scenario, rules_path: str) -> dict:
    """跑一个场景，返回指标和 pass/fail。"""
    grid = scenario.grid_factory()
    sim = Simulator(grid, dt=1.0, verbose=False)
    engine = load_engine_from_yaml(rules_path, name=f"engine_{scenario.name}")

    df = sim.run(scenario.duration, scenario.schedule, rules=engine)

    conv = df[df["converged"]]
    n_total = len(df)
    n_conv = len(conv)

    if len(conv) == 0:
        return {
            "name": scenario.name,
            "category": scenario.category,
            "description": scenario.description,
            "n_total": n_total,
            "n_conv": 0,
            "min_v": 0.0,
            "max_load_pct": 9999.0,
            "max_loss_mw": 9999.0,
            "blackout_steps": 9999,
            "rule_fires": 0,
            "passed": False,
            "fail_reasons": ["PF never converged"],
        }

    v_cols = [c for c in conv.columns if c.startswith("v_")]
    line_cols = [c for c in conv.columns if c.startswith("line_")]

    min_v = float(conv[v_cols].min().min())
    max_load = float(conv[line_cols].max().max())
    max_loss = float(conv["loss_mw"].max())

    blackout = 0
    if scenario.key_v_bus and f"v_{scenario.key_v_bus}" in conv.columns:
        blackout = int((conv[f"v_{scenario.key_v_bus}"] < 0.01).sum())

    # 通过判据
    crit = scenario.pass_criteria
    fails = []
    if n_conv < n_total:
        fails.append(f"PF 不收敛 ({n_conv}/{n_total})")
    if min_v < crit.min_v:
        fails.append(f"最低电压 {min_v:.4f} < {crit.min_v}")
    if max_load > crit.max_load_pct:
        fails.append(f"最大载流 {max_load:.1f}% > {crit.max_load_pct}")
    if blackout > crit.max_blackout_steps:
        fails.append(f"失电 {blackout} 步 > {crit.max_blackout_steps}")

    return {
        "name": scenario.name,
        "category": scenario.category,
        "description": scenario.description,
        "n_total": n_total,
        "n_conv": n_conv,
        "min_v": min_v,
        "max_load_pct": max_load,
        "max_loss_mw": max_loss,
        "blackout_steps": blackout,
        "rule_fires": len(engine.log),
        "passed": len(fails) == 0,
        "fail_reasons": fails,
    }


def main():
    print("=" * 70)
    print(f"基准测试套件（规则集：{RULES_YAML}）")
    print("=" * 70)

    results = []
    for sc in SCENARIOS:
        print(f"\n>>> 运行: {sc.name}")
        r = evaluate_scenario(sc, RULES_YAML)
        results.append(r)
        status = "PASS" if r["passed"] else "FAIL"
        print(f"    {status}  min_v={r['min_v']:.4f}  "
              f"max_load={r['max_load_pct']:.1f}%  blackout={r['blackout_steps']}  "
              f"fires={r['rule_fires']}")
        if not r["passed"]:
            for reason in r["fail_reasons"]:
                print(f"      - {reason}")

    df = pd.DataFrame(results)
    pass_rate = 100 * df["passed"].sum() / len(df)

    print("\n" + "=" * 70)
    print(f"汇总：通过 {df['passed'].sum()}/{len(df)} ({pass_rate:.0f}%)")
    print("=" * 70)
    print(df[["name", "category", "min_v", "max_load_pct",
              "blackout_steps", "rule_fires", "passed"]].to_string(index=False))

    # 按 category 统计
    print("\n按 category 通过率：")
    cat_summary = df.groupby("category").agg(
        total=("name", "size"),
        passed=("passed", "sum"),
        min_v_avg=("min_v", "mean"),
        max_load_avg=("max_load_pct", "mean"),
    )
    cat_summary["pass_rate_%"] = (100 * cat_summary["passed"] / cat_summary["total"]).round(0)
    print(cat_summary.to_string())

    # 画图
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle("基准测试套件结果", fontsize=13)

    colors = ["green" if p else "red" for p in df["passed"]]

    # 1. 最低电压
    ax = axes[0, 0]
    ax.barh(df["name"], df["min_v"], color=colors, alpha=0.8)
    ax.axvline(0.95, color="blue", ls="--", lw=0.8, label="0.95 阈值")
    ax.set_xlabel("最低电压 (pu)")
    ax.set_title("最低电压（绿色=PASS，红色=FAIL）")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)
    ax.invert_yaxis()

    # 2. 最大载流
    ax = axes[0, 1]
    ax.barh(df["name"], df["max_load_pct"], color=colors, alpha=0.8)
    ax.axvline(100, color="red", ls="--", lw=0.8, label="100% 热稳定")
    ax.set_xlabel("最大载流 (%)")
    ax.set_title("最大载流")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.invert_yaxis()

    # 3. 失电时长
    ax = axes[1, 0]
    ax.barh(df["name"], df["blackout_steps"], color=colors, alpha=0.8)
    ax.set_xlabel("失电步数")
    ax.set_title("关键母线失电时长")
    ax.grid(True, alpha=0.3)
    ax.invert_yaxis()

    # 4. 规则触发次数
    ax = axes[1, 1]
    ax.barh(df["name"], df["rule_fires"], color="steelblue", alpha=0.8)
    ax.set_xlabel("规则触发次数")
    ax.set_title("每个场景的规则触发次数")
    ax.grid(True, alpha=0.3)
    ax.invert_yaxis()

    plt.tight_layout()
    out = "lab_scripts/exp10_benchmark.png"
    plt.savefig(out, dpi=120)
    print(f"\n图已保存到 {out}")

    # 保存 CSV
    csv_out = "lab_scripts/exp10_benchmark.csv"
    df.to_csv(csv_out, index=False, encoding="utf-8-sig")
    print(f"结果已保存到 {csv_out}")


if __name__ == "__main__":
    main()
