# -*- coding: utf-8 -*-
"""
实验十三：概率潮流（Probabilistic Power Flow, PPF）
==================================================
用蒙特卡洛方法估计电网状态的统计分布：

  1. 给所有负荷加随机扰动（±10% 正态分布）
  2. 跑 N=200 次潮流仿真
  3. 收集每个节点电压、每条支路载流的统计分布
  4. 输出均值、标准差、5%/95% 分位数、违反率

输出：
  - 各母线电压直方图
  - 关键节点 V_min/V_max 时序带状图（均值 ± 2σ）
  - 违反率表（V < 0.95 pu 或 loading > 100% 的概率）

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp13_ppf.py
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

import VeraGridEngine as vg
from event_sim import Simulator, snapshot

GRID_FILE = "Grids_and_profiles/grids/IEEE 14 bus.raw"
N_MC = 200  # 蒙特卡洛次数
NOISE_STD = 0.10  # 负荷扰动标准差（10%）


def add_random_perturbation(grid, rng: np.random.Generator, std: float = NOISE_STD):
    """给所有负荷加正态扰动。返回扰动后的 P/Q 列表。"""
    perturbations = []
    for ld in grid.get_loads():
        factor = 1.0 + rng.normal(0, std)
        ld.P *= factor
        ld.Q *= factor
        perturbations.append((ld.name, factor))
    return perturbations


def run_monte_carlo(n_runs: int = N_MC, seed: int = 42):
    """运行 N 次蒙特卡洛仿真。"""
    rng = np.random.default_rng(seed)

    # 记录每个 (bus, t=0) 的电压，每个 (line, t=0) 的 loading
    voltage_samples = {b.name: [] for b in vg.open_file(GRID_FILE).buses}
    loading_samples = {ln.name: [] for ln in vg.open_file(GRID_FILE).lines}

    for i in range(n_runs):
        grid = vg.open_file(GRID_FILE)
        # 加扰动
        add_random_perturbation(grid, rng)
        # 跑基线潮流
        pf = vg.power_flow(grid,
                           options=vg.PowerFlowOptions(solver_type=vg.SolverType.NR))
        if not pf.converged:
            continue
        snap = snapshot(grid, pf, t=0.0)
        for bname in voltage_samples:
            v = snap.get(f"v_{bname}", np.nan)
            voltage_samples[bname].append(v if v is not None else np.nan)
        for lname in loading_samples:
            ld_val = snap.get(f"line_{lname}", np.nan)
            loading_samples[lname].append(ld_val if ld_val is not None else np.nan)

    # 汇总统计
    v_stats = []
    for bname, samples in voltage_samples.items():
        arr = np.array([s for s in samples if s is not None and not np.isnan(s)])
        if len(arr) == 0:
            continue
        v_stats.append({
            "bus": bname,
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "p05": float(np.percentile(arr, 5)),
            "p95": float(np.percentile(arr, 95)),
            "viol_low": float(np.mean(arr < 0.95)),
            "viol_high": float(np.mean(arr > 1.05)),
        })
    v_df = pd.DataFrame(v_stats)

    l_stats = []
    for lname, samples in loading_samples.items():
        arr = np.array([s for s in samples if s is not None and not np.isnan(s)])
        if len(arr) == 0:
            continue
        l_stats.append({
            "line": lname,
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "p95": float(np.percentile(arr, 95)),
            "viol": float(np.mean(arr > 100.0)),
        })
    l_df = pd.DataFrame(l_stats)

    return v_df, l_df, voltage_samples, loading_samples


def main():
    print("=" * 70)
    print(f"Phase E: 概率潮流（蒙特卡洛 N={N_MC}, 扰动标准差={NOISE_STD*100:.0f}%）")
    print("=" * 70)

    print(f"\n运行 {N_MC} 次蒙特卡洛仿真...")
    v_df, l_df, v_samples, l_samples = run_monte_carlo()

    print("\n=== 各母线电压统计 ===")
    print(v_df.to_string(index=False))

    print("\n=== 各线路载流统计 ===")
    print(l_df.to_string(index=False))

    print("\n=== 违反率（节点 V < 0.95 pu 或线路 loading > 100%）===")
    for _, r in v_df.iterrows():
        if r["viol_low"] > 0.01 or r["viol_high"] > 0.01:
            print(f"  母线 {r['bus']}: 低压违反 {r['viol_low']*100:.1f}%, 高压 {r['viol_high']*100:.1f}%")
    for _, r in l_df.iterrows():
        if r["viol"] > 0.01:
            print(f"  线路 {r['line']}: 过载概率 {r['viol']*100:.1f}%")

    # ---- 画图
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(f"概率潮流结果（蒙特卡洛 N={N_MC}, 扰动 {NOISE_STD*100:.0f}%）", fontsize=13)

    # 1. 母线电压分布（散点图：mean ± std）
    ax = axes[0, 0]
    bus_names = v_df["bus"].tolist()
    means = v_df["mean"].values
    stds = v_df["std"].values
    x = np.arange(len(bus_names))
    ax.errorbar(x, means, yerr=2*stds, fmt="o", capsize=4, color="steelblue")
    ax.axhline(0.95, color="red", ls="--", lw=0.7, label="下限 0.95")
    ax.axhline(1.05, color="red", ls="--", lw=0.7, label="上限 1.05")
    ax.set_xticks(x)
    ax.set_xticklabels(bus_names, rotation=45, fontsize=8)
    ax.set_ylabel("电压 (pu)")
    ax.set_title("母线电压 mean ± 2σ")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 2. 母线电压直方图（选 BUS 14）
    ax = axes[0, 1]
    bus14 = np.array([s for s in v_samples["BUS 14"] if s is not None and not np.isnan(s)])
    ax.hist(bus14, bins=30, color="lightblue", edgecolor="black", alpha=0.8)
    ax.axvline(0.95, color="red", ls="--", lw=0.8, label="0.95")
    ax.axvline(bus14.mean(), color="blue", ls="-", lw=1.5, label=f"mean={bus14.mean():.4f}")
    ax.set_xlabel("电压 (pu)")
    ax.set_ylabel("频次")
    ax.set_title(f"BUS 14 电压分布（N={len(bus14)}）")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # 3. 线路载流分布
    ax = axes[1, 0]
    line_names = l_df["line"].tolist()
    load_means = l_df["mean"].values
    load_p95 = l_df["p95"].values
    x = np.arange(len(line_names))
    ax.bar(x - 0.2, load_means, 0.4, label="mean", color="steelblue", alpha=0.8)
    ax.bar(x + 0.2, load_p95, 0.4, label="P95", color="salmon", alpha=0.8)
    ax.axhline(100, color="red", ls="--", lw=0.8, label="100% 热稳定")
    ax.set_xticks(x)
    ax.set_xticklabels(line_names, rotation=45, fontsize=8)
    ax.set_ylabel("载流 (%)")
    ax.set_title("线路载流 mean vs P95")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # 4. 违反率表（柱状图）
    ax = axes[1, 1]
    violations = []
    for _, r in v_df.iterrows():
        violations.append((f"V_{r['bus']}_low", r["viol_low"]*100))
    for _, r in l_df.iterrows():
        if r["viol"] > 0:
            violations.append((f"L_{r['line']}_over", r["viol"]*100))
    if violations:
        names, vals = zip(*violations)
        ax.barh(range(len(names)), vals, color="red", alpha=0.8)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=7)
        ax.set_xlabel("违反概率 (%)")
        ax.set_title("节点/线路违反概率")
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, "无违反", ha="center", va="center",
                transform=ax.transAxes, fontsize=14)

    plt.tight_layout()
    out = "lab_scripts/exp13_ppf.png"
    plt.savefig(out, dpi=120)
    print(f"\n图已保存到 {out}")

    # 保存 CSV
    v_df.to_csv("lab_scripts/exp13_voltage_stats.csv", index=False, encoding="utf-8-sig")
    l_df.to_csv("lab_scripts/exp13_loading_stats.csv", index=False, encoding="utf-8-sig")
    print("统计数据已保存到 exp13_*_stats.csv")


if __name__ == "__main__":
    main()
