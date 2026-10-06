# -*- coding: utf-8 -*-
"""
实验三：事件驱动的电网仿真（Phase 1 验证）
================================================
目标：在 IEEE 14 上验证事件注入器闭环

剧情：
  t=  0s  基线
  t= 10s  BUS 14 突然增加 50MW 工厂负荷（事件 1）
  t= 25s  BUS 9 增加 30MW（事件 2）
  t= 40s  发电机 G2_1 跳机（事件 3）
  t= 55s  线路 2_4_1 跳闸（事件 4）
  t= 70s  BUS 14 撤掉那 50MW（事件 5，恢复）

观察：
  - 各节点电压轨迹（特别是 BUS 9 / BUS 14）
  - 关键线路 loading
  - 发电机出力变化（slack 是否吸收差额）
  - 总损耗

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp03_event_driven_sim.py
"""

import os
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import matplotlib
matplotlib.use("Agg")  # 无头环境也能存图
import matplotlib.pyplot as plt

import VeraGridEngine as vg
from event_sim import Simulator, make_schedule, summarize_events

GRID_FILE = "Grids_and_profiles/grids/IEEE 14 bus.raw"


def main():
    grid = vg.open_file(GRID_FILE)
    print(f"加载电网: {len(grid.buses)} 母线  "
          f"{len(grid.lines)} 线路  "
          f"{len(grid.get_generators())} 发电机  "
          f"{len(grid.get_loads())} 负荷\n")

    # ------------------- 事件剧本
    schedule = make_schedule(
        (10.0, "load_add",  "BUS 14", 50.0),
        (25.0, "load_add",  "BUS 9",  30.0),
        (40.0, "gen_trip",  "2_1"),       # BUS 2 上的发电机跳机
        (55.0, "line_trip", "2_4_1"),     # BUS 2-4 的线路断开
        (70.0, "load_drop", "_evt_1"),    # 撤掉 t=10s 加的那个负荷
    )

    print("事件时间表：")
    for ev in schedule:
        print(f"  t={ev.t:5.1f}s  {ev.kind:<10s}  {ev.target}  "
              f"{f'(+{ev.magnitude}MW)' if ev.magnitude else ''}")
    print()

    # ------------------- 跑仿真
    sim = Simulator(grid, dt=1.0, verbose=True)
    df = sim.run(duration=90.0, schedule=schedule)

    # ------------------- 打印关键指标
    print("\n=== 关键事件时刻的电压/载流/损耗 ===\n")
    sample_times = [0.0, 10.0, 25.0, 40.0, 55.0, 70.0, 90.0]
    key_buses = ["BUS 1", "BUS 2", "BUS 4", "BUS 9", "BUS 14"]
    key_lines = ["2_4_1", "2_5_1", "4_5_1", "1_2_1"]

    header = f"{'t':>5s} | {'cv':>4s} | " + " ".join(f"{b:>7s}" for b in key_buses) \
             + " | " + " ".join(f"{l:>7s}" for l in key_lines) + " | loss"
    print(header)
    print("-" * len(header))
    for t in sample_times:
        snap = df[df["t"] == t].iloc[0]
        cv = " OK " if snap["converged"] else "FAIL"
        vs = " ".join(f"{snap[f'v_{b}']:7.4f}" if not np.isnan(snap.get(f'v_{b}', np.nan)) else f"{'NaN':>7s}"
                      for b in key_buses)
        ls = " ".join(f"{snap[f'line_{l}']:7.2f}" if not np.isnan(snap.get(f'line_{l}', np.nan)) else f"{'NaN':>7s}"
                      for l in key_lines)
        loss = f"{snap['loss_mw']:6.2f}" if not np.isnan(snap["loss_mw"]) else "  NaN"
        print(f"{t:5.0f} | {cv:>4s} | {vs} | {ls} | {loss:>6s}MW")

    # ------------------- 画图
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    fig.suptitle("IEEE 14 事件驱动仿真（Phase 1 验证）", fontsize=13)

    # 图 1：关键节点电压轨迹
    ax = axes[0]
    for b in key_buses:
        col = f"v_{b}"
        if col in df.columns:
            ax.plot(df["t"], df[col], label=b, marker="o", markersize=2)
    ax.axhline(1.05, color="r", ls="--", lw=0.8, alpha=0.6, label="上限 1.05 pu")
    ax.axhline(0.95, color="r", ls="--", lw=0.8, alpha=0.6, label="下限 0.95 pu")
    # 事件竖线
    for ev in schedule:
        ax.axvline(ev.t, color="gray", ls=":", lw=0.6, alpha=0.5)
    ax.set_ylabel("电压 (pu)")
    ax.set_ylim(0.85, 1.15)
    ax.legend(loc="lower left", ncol=3, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_title("节点电压")

    # 图 2：关键线路 loading
    ax = axes[1]
    for l in key_lines:
        col = f"line_{l}"
        if col in df.columns:
            ax.plot(df["t"], df[col], label=l, marker="o", markersize=2)
    ax.axhline(100, color="r", ls="--", lw=0.8, alpha=0.6, label="100% 热稳定")
    for ev in schedule:
        ax.axvline(ev.t, color="gray", ls=":", lw=0.6, alpha=0.5)
    ax.set_ylabel("Loading (%)")
    ax.legend(loc="upper left", ncol=3, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_title("线路载流")

    # 图 3：发电机出力
    ax = axes[2]
    gen_names = [gen.name for gen in grid.get_generators()]
    for g in gen_names:
        col = f"gen_{g}"
        if col in df.columns:
            ax.plot(df["t"], df[col], label=g, marker="o", markersize=2)
    for ev in schedule:
        ax.axvline(ev.t, color="gray", ls=":", lw=0.6, alpha=0.5)
    ax.set_xlabel("时间 (s)")
    ax.set_ylabel("P (MW)")
    ax.legend(loc="upper left", ncol=3, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_title("发电机出力")

    plt.tight_layout()
    out_png = "lab_scripts/exp03_event_driven_sim.png"
    plt.savefig(out_png, dpi=120)
    print(f"\n图已保存到 {out_png}")

    # ------------------- 不收敛统计
    n_total = len(df)
    n_conv = df["converged"].sum()
    print(f"\n收敛统计: {n_conv}/{n_total} 步成功 (不收敛通常意味着系统崩溃)")


if __name__ == "__main__":
    main()
