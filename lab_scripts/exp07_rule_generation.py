# -*- coding: utf-8 -*-
"""
实验七：规则生成（Phase 4 验证）
================================================
目标：在辐射状 feeder 上枚举候选规则，仿真评估打分，输出 top-N 规则

拓扑：5-bus 双馈线 + TIE（radial_feeder.py）
场景：S01 跳闸后 F1B 失电

候选空间：
  UVLS:    V<{0.90,0.92,0.94,0.96} -> shed {10,20,30,50}% @ *
           = 16 条
  OVERLOAD: loading>{110,130,150,170}% -> shed {5,10,20}% @ *
           = 12 条
  RECONF:  blackout -> close TIE
           = 1 条
  共 29 条候选

评分：综合最低电压、最大载流、失电时长、损耗、切负荷量
排名：score 降序

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp07_rule_generation.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

for cand in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS"):
    if any(cand in f.name for f in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [cand]
        break
plt.rcParams["axes.unicode_minus"] = False

from event_sim import make_schedule
from rule_generator import (
    Scenario, RuleSpec,
    gen_uvls_candidates, gen_overload_candidates, gen_reconf_candidates,
    run_search,
)
from radial_feeder import build_radial_feeder, LN_S01, LN_TIE, BUS_F1B


def grid_factory():
    """每次评估都返回新 feeder（避免状态污染）。"""
    return build_radial_feeder()


def heavy_grid_factory():
    """高负荷 + 低线路限额版本：转供后会过载，触发复合规则需求。"""
    return build_radial_feeder(load_p=10.0, load_q=3.5, line_rate=12.0)


def main():
    # 两个场景对比：常规 vs 高负荷（后者需要复合规则）
    scenario = Scenario(
        name="S01_trip_light",
        duration=40.0,
        schedule=make_schedule(
            (5.0,  "line_trip",  LN_S01),
            (30.0, "line_close", LN_S01),
            (30.0, "line_trip",  LN_TIE),
        ),
        grid_factory=grid_factory,
    )

    scenario_heavy = Scenario(
        name="S01_trip_heavy",
        duration=40.0,
        schedule=make_schedule(
            (5.0,  "line_trip",  LN_S01),
            (30.0, "line_close", LN_S01),
            (30.0, "line_trip",  LN_TIE),
        ),
        grid_factory=heavy_grid_factory,
    )

    # ---- 生成候选规则
    print("=" * 60)
    print("生成候选规则...")
    print("=" * 60)
    specs = []
    specs += gen_uvls_candidates(
        v_thresholds=(0.90, 0.92, 0.94, 0.96),
        shed_fractions=(0.1, 0.2, 0.3, 0.5),
    )
    specs += gen_overload_candidates(
        load_thresholds=(110.0, 130.0, 150.0, 170.0),
        shed_fractions=(0.05, 0.10, 0.20),
    )
    specs += gen_reconf_candidates(tie_switches=(LN_TIE,))
    print(f"  UVLS 候选: 16")
    print(f"  OVERLOAD 候选: 12")
    print(f"  RECONF 候选: 1")
    print(f"  合计: {len(specs)} 条")

    # ---- 评估搜索
    print("\n" + "=" * 60)
    print("开始枚举评估...")
    print("=" * 60)
    df, baseline = run_search(scenario, specs, baseline_grid_factory=grid_factory,
                              top_n=10, verbose=True)

    # ---- 复合规则测试（场景 A：轻负荷）
    print("\n" + "=" * 60)
    print("复合规则评估（场景 A：轻负荷）")
    print("=" * 60)
    from rule_generator import evaluate_compound, RuleSpec

    top_reconf = next(s for s in specs if s.family == "RECONF")
    top_uvls = df[df["family"] == "UVLS"].iloc[0]
    top_ovl = df[df["family"] == "OVERLOAD"].iloc[0]
    best_uvls_spec = next(s for s in specs if s.name == top_uvls["name"])
    best_ovl_spec = next(s for s in specs if s.name == top_ovl["name"])

    compounds = [
        ("RECONF_only", [top_reconf]),
        ("RECONF+UVLS", [top_reconf, best_uvls_spec]),
        ("RECONF+OVL", [top_reconf, best_ovl_spec]),
        ("RECONF+UVLS+OVL", [top_reconf, best_uvls_spec, best_ovl_spec]),
        ("UVLS+OVL", [best_uvls_spec, best_ovl_spec]),
    ]

    compound_rows = []
    for name, spec_list in compounds:
        score, m = evaluate_compound(spec_list, scenario, compound_name=name)
        row = {"name": name, "family": "COMPOUND", "score": score,
               "description": "+".join(s.name for s in spec_list), **m}
        compound_rows.append(row)
        print(f"  {name:<20s}  score={score:8.2f}  min_v={m.get('min_v', 0):.4f}  "
              f"max_load={m.get('max_load', 0):5.1f}%  blackout={m.get('blackout_steps', 0):2d}")

    # 把复合规则结果加入总表
    df_all = pd.concat([df, pd.DataFrame(compound_rows)], ignore_index=True)
    df_all = df_all.sort_values("score", ascending=False).reset_index(drop=True)
    df_all["rank"] = df_all.index + 1

    print("\n合并排名（单规则 + 复合规则，场景 A）：")
    cols = ["rank", "family", "score", "min_v", "max_load", "blackout_steps", "name"]
    print(df_all[cols].head(10).to_string(index=False))

    # ---- 场景 B：高负荷 —— 复合规则应能胜过单规则
    print("\n" + "=" * 60)
    print("场景 B：高负荷（每条馈线 6MW，TIE 转供会过载）")
    print("=" * 60)
    df_heavy, baseline_heavy = run_search(scenario_heavy, specs,
                                          baseline_grid_factory=heavy_grid_factory,
                                          top_n=5, verbose=False)

    compound_rows_heavy = []
    for name, spec_list in compounds:
        score, m = evaluate_compound(spec_list, scenario_heavy, compound_name=name)
        row = {"name": name, "family": "COMPOUND", "score": score,
               "description": "+".join(s.name for s in spec_list), **m}
        compound_rows_heavy.append(row)
        print(f"  {name:<20s}  score={score:8.2f}  min_v={m.get('min_v', 0):.4f}  "
              f"max_load={m.get('max_load', 0):5.1f}%  blackout={m.get('blackout_steps', 0):2d}")

    df_heavy_all = pd.concat([df_heavy, pd.DataFrame(compound_rows_heavy)],
                             ignore_index=True)
    df_heavy_all = df_heavy_all.sort_values("score", ascending=False).reset_index(drop=True)
    df_heavy_all["rank"] = df_heavy_all.index + 1

    print("\n场景 B 合并排名（前 8）：")
    print(df_heavy_all[["rank", "family", "score", "min_v", "max_load",
                        "blackout_steps", "name"]].head(8).to_string(index=False))

    # ---- 按 family 分组看
    print("\n" + "=" * 60)
    print("按 family 聚合")
    print("=" * 60)
    fam = df.groupby("family").agg(
        count=("name", "size"),
        mean_score=("score", "mean"),
        best_score=("score", "max"),
        best_rule=("name", lambda s: df.loc[df["score"].iloc[s.index].idxmax(), "name"]
                   if len(s) > 0 else ""),
        best_min_v=("min_v", "max"),
        best_blackout=("blackout_steps", "min"),
    )
    print(fam.to_string())

    # ---- 画图：候选规则得分分布
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    fig.suptitle("Phase 4 规则生成 — 单规则 vs 复合规则对比", fontsize=13)

    # 左上：单规则 vs 复合规则 在两个场景下的得分
    ax = axes[0, 0]
    cmp_names = [r["name"] for r in compound_rows]
    cmp_scores_A = [r["score"] for r in compound_rows]
    cmp_scores_B = [r["score"] for r in compound_rows_heavy]
    x = np.arange(len(cmp_names))
    w = 0.35
    ax.bar(x - w/2, cmp_scores_A, w, label="场景 A 轻负荷", color="lightblue")
    ax.bar(x + w/2, cmp_scores_B, w, label="场景 B 高负荷", color="salmon")
    ax.set_xticks(x)
    ax.set_xticklabels(cmp_names, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Score（越高越好）")
    ax.set_title("复合规则在两个场景下的得分对比")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color="gray", ls=":", lw=0.5)

    # 右上：场景 B 的 max_load（关键差异点）
    ax = axes[0, 1]
    cmp_loads_B = [r.get("max_load", 0) for r in compound_rows_heavy]
    ax.bar(x, cmp_loads_B, color="salmon", alpha=0.8)
    ax.axhline(100, color="r", ls="--", lw=0.8, label="100% 热稳定")
    ax.set_xticks(x)
    ax.set_xticklabels(cmp_names, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Max Loading (%)")
    ax.set_title("场景 B（高负荷）下的最大载流")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # 左下：场景 B 各单规则得分
    ax = axes[1, 0]
    fam_color = {"UVLS": "blue", "OVERLOAD": "green", "RECONF": "red"}
    for fam, sub in df_heavy.groupby("family"):
        ax.scatter(sub["max_load"], sub["score"], c=fam_color[fam],
                   label=fam, s=80, alpha=0.7, edgecolors="black", lw=0.5)
    # 复合规则用大星标
    for r in compound_rows_heavy:
        ax.scatter(r.get("max_load", 0), r["score"], c="gold", marker="*",
                   s=300, edgecolors="black", lw=1.0,
                   label="compound" if r["name"] == cmp_names[0] else None)
    ax.set_xlabel("Max Loading (%)")
    ax.set_ylabel("Score")
    ax.set_title("场景 B：score vs max_load（★ = 复合规则）")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 右下：场景 A vs B 同一规则名对比
    ax = axes[1, 1]
    a_keys = ["min_v", "max_load", "shed_mw"]
    a_labels = ["最低电压", "最大载流", "切负荷量"]
    A_metrics = {k: df.iloc[0].get(k, 0) for k in a_keys}
    # 找场景 B 中最佳单规则
    best_B_single = df_heavy[df_heavy["family"] != "COMPOUND"].iloc[0]
    B_metrics = {k: best_B_single.get(k, 0) for k in a_keys}
    x2 = np.arange(len(a_keys))
    w2 = 0.35
    A_vals = [A_metrics[k] for k in a_keys]
    B_vals = [B_metrics[k] for k in a_keys]
    ax.bar(x2 - w2/2, A_vals, w2, label="场景 A 最佳", color="lightblue")
    ax.bar(x2 + w2/2, B_vals, w2, label="场景 B 最佳单规则", color="salmon")
    ax.set_xticks(x2)
    ax.set_xticklabels(a_labels)
    ax.set_title("场景 A vs 场景 B 最佳单规则指标")
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = "lab_scripts/exp07_rule_generation.png"
    plt.savefig(out, dpi=120)
    print(f"\n图已保存到 {out}")

    # ---- 保存结果到 CSV
    csv_out = "lab_scripts/exp07_results.csv"
    df_all.to_csv(csv_out, index=False, encoding="utf-8-sig")
    print(f"\n场景 A 完整结果已保存到 {csv_out}")

    csv_out_B = "lab_scripts/exp07_results_heavy.csv"
    df_heavy_all.to_csv(csv_out_B, index=False, encoding="utf-8-sig")
    print(f"场景 B 完整结果已保存到 {csv_out_B}")

    # ---- 结论
    print("\n" + "=" * 60)
    print("结论")
    print("=" * 60)
    print("\n【场景 A：轻负荷】")
    top_A = df_all.iloc[0]
    print(f"  最佳规则: {top_A['name']}  (score={top_A['score']:.2f})")
    print(f"  最低电压 {top_A['min_v']:.4f} pu, 最大载流 {top_A['max_load']:.1f}%, 失电 {top_A['blackout_steps']} 步")

    print("\n【场景 B：高负荷（每馈线 6MW）】")
    top_B = df_heavy_all.iloc[0]
    print(f"  最佳规则: {top_B['name']}  (score={top_B['score']:.2f})")
    print(f"  最低电压 {top_B['min_v']:.4f} pu, 最大载流 {top_B['max_load']:.1f}%, 失电 {top_B['blackout_steps']} 步")

    print("\n【关键发现】")
    if df_heavy_all.iloc[0]["family"] == "COMPOUND":
        print("  ✓ 场景 B 中复合规则胜过所有单规则（高负荷下需要 RECONF + 切负荷双管齐下）")
    else:
        print("  - 本场景下最佳仍是单规则；可考虑更复杂场景或更细的候选动作")


if __name__ == "__main__":
    main()
