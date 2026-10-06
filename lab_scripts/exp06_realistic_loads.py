# -*- coding: utf-8 -*-
"""
实验六：真实负荷扰动（Phase B 验证）
================================================
目标：在 IEEE 14 上验证 ZIP 模型、闪变、随机启停三类真实负荷特性

场景：
  t= 0~30s    稳态运行（含闪变，可见电压小幅波动）
  t=30s      BUS 14 突然接一个工厂负荷（含间歇停机）
  t=60s      BUS 9 突然接一个变频器负荷（含 8Hz 闪变）
  t=120s     观察一段时间的随机启停
  t=180s     撤掉新加的两个负荷

负荷预设：
  工厂：zip_p=0.5（偏恒功率异步电机）+ 低概率停机
  变频器：zip_p=1.0（纯恒功率）+ 8Hz 5% 闪变
  居民：zip_z=0.6（偏恒阻抗照明）+ 高概率启停

观察：
  - BUS 14 / BUS 9 电压轨迹（闪变叠加）
  - 各 profile 的实际 P/Q 时序（看 ZIP 折算和闪烁）
  - 工厂负荷的随机停机事件
  - 与 R001/R003 规则协同

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp06_realistic_loads.py
"""

import warnings
warnings.filterwarnings("ignore")

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

import VeraGridEngine as vg
from event_sim import Simulator, make_schedule
from rule_engine import build_default_rules, RuleEngine
from load_profiles import (
    LoadProfiler, LoadProfile,
    industrial_factory, vfd_load, residential,
)

GRID_FILE = "Grids_and_profiles/grids/IEEE 14 bus.raw"


def main():
    grid = vg.open_file(GRID_FILE)
    print(f"加载电网: {len(grid.buses)} 母线")

    # ---------- 创建 profiler
    profiler = LoadProfiler(seed=42)

    # 把现有负荷改成"居民"模板（中等随机启停 + 偏恒阻抗）
    bus_with_loads = {
        "BUS 3": (94.2, 19.0), "BUS 4": (47.8, -3.9),
        "BUS 5": (7.6, 1.6), "BUS 9": (29.5, 16.6),
        "BUS 10": (9.0, 5.8), "BUS 11": (3.5, 1.8),
        "BUS 12": (6.1, 1.6), "BUS 13": (13.5, 5.8),
        "BUS 14": (14.9, 5.0),
    }
    for bus_name, (p, q) in bus_with_loads.items():
        profiler.add(residential(bus_name, p, q))

    # ---------- 事件剧本：动态加工厂和变频器负荷
    schedule = make_schedule(
        (30.0, "load_add", "BUS 14", 25.0),   # 工厂
        (60.0, "load_add", "BUS 9",  15.0),   # 变频器
        (180.0, "load_drop", "_evt_1"),       # 撤工厂
        (180.0, "load_drop", "_evt_2"),       # 撤变频器
    )

    # ---------- 规则（用低阈值，让闪变容易触发 UVLS 观测）
    rules = build_default_rules(
        v_under=0.95,                # 收紧一点，便于观察
        v_over=1.10,
        line_overload_pct=140.0,
        shed_fraction_uv=0.20,
        shed_fraction_overload=0.10,
        cooldown=3.0,
    )
    # 给 BUS 9/BUS 14 后期附加动态 profile（标记 _evt_1 为工厂，_evt_2 为变频器）
    # 我们需要监听事件 → 加载 profile

    # 由于事件注入的 _evt_N 名字由 _load_counter 决定，我们用 on_event 回调
    new_load_profiles = []  # 待添加的 profile（在 on_event 里加入）

    def on_event(ev, msg):
        if ev.kind == "load_add":
            if ev.target == "BUS 14":
                # 工厂负荷
                prof = industrial_factory("BUS 14", base_p=ev.magnitude,
                                          base_q=ev.magnitude * 0.3)
                profiler.add(prof)
                print(f"  >> 注册 profile: {prof.label}")
            elif ev.target == "BUS 9":
                # 变频器负荷
                prof = vfd_load("BUS 9", base_p=ev.magnitude,
                                base_q=ev.magnitude * 0.2)
                profiler.add(prof)
                print(f"  >> 注册 profile: {prof.label}")

    engine = RuleEngine(rules, name="phase_b")

    # ---------- 跑仿真
    sim = Simulator(grid, dt=1.0, verbose=False, profiler=profiler)
    df = sim.run(duration=200.0, schedule=schedule, rules=engine, on_event=on_event)

    # ---------- 输出统计
    print("\n=== 仿真结果 ===")
    n_total = len(df)
    n_conv = int(df["converged"].sum())
    print(f"总步数 {n_total}，收敛 {n_conv} 步 ({100*n_conv/n_total:.1f}%)")
    print(f"规则触发: {len(engine.log)} 次")
    by_rule = {}
    for t, rid, msg in engine.log:
        by_rule.setdefault(rid, []).append((t, msg[:60]))
    for rid, items in by_rule.items():
        print(f"  {rid}: {len(items)} 次")
        if len(items) <= 3:
            for t, m in items:
                print(f"    t={t}: {m}")

    # ---------- 负荷时序历史
    prof_df = profiler.history_dataframe()
    print(f"\nProfiler 历史: {len(prof_df)} 条记录")
    print(f"profile 数: {prof_df['load'].nunique()}")
    print(prof_df.groupby("load")["state"].agg(["mean", "sum"]).rename(
        columns={"mean": "运行率", "sum": "运行步数"}))

    # ---------- 画图
    fig, axes = plt.subplots(4, 1, figsize=(12, 12), sharex=True)
    fig.suptitle("Phase B 真实负荷扰动（IEEE 14 + ZIP/闪变/启停）", fontsize=13)

    # 上1：关键母线电压
    ax = axes[0]
    for b in ["BUS 3", "BUS 9", "BUS 14"]:
        col = f"v_{b}"
        if col in df.columns:
            ax.plot(df["t"], df[col], label=b, lw=0.9)
    ax.axhline(0.95, color="r", ls="--", lw=0.6, alpha=0.5)
    ax.axhline(1.05, color="r", ls="--", lw=0.6, alpha=0.5)
    ax.set_ylabel("V (pu)")
    ax.set_title("母线电压（含闪变可见小幅波动）")
    ax.legend(loc="lower right", fontsize=8, ncol=3)
    ax.grid(True, alpha=0.3)

    # 上2：BUS 9 电压细节（看 8Hz 闪变）
    ax = axes[1]
    col = "v_BUS 9"
    if col in df.columns:
        ax.plot(df["t"], df[col], lw=0.6, color="orange")
        # 标出 60s 后变频器接入
        ax.axvline(60, color="purple", ls="--", lw=0.8, alpha=0.6, label="VFD 接入")
        ax.axvline(180, color="gray", ls="--", lw=0.8, alpha=0.6, label="撤负荷")
    ax.set_ylabel("V_BUS 9 (pu)")
    ax.set_title("BUS 9 电压细节（变频器 8Hz 闪变）")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, alpha=0.3)

    # 上3：profile 时序
    ax = axes[2]
    for load_name in prof_df["load"].unique():
        sub = prof_df[prof_df["load"] == load_name]
        if "VFD" in load_name or "变频器" in load_name:
            ax.plot(sub["t"], sub["P"], label=load_name, lw=1.0, alpha=0.8)
        elif "工厂" in load_name:
            ax.plot(sub["t"], sub["P"], label=load_name, lw=1.5, alpha=0.9)
        elif "居民@BUS 14" in load_name:
            ax.plot(sub["t"], sub["P"], label=load_name, lw=0.7, alpha=0.5, color="gray")
        elif "居民@BUS 9" in load_name:
            ax.plot(sub["t"], sub["P"], label=load_name, lw=0.7, alpha=0.5, color="brown")
    ax.set_ylabel("P (MW)")
    ax.set_title("负荷时序（工厂/变频器/居民）")
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.grid(True, alpha=0.3)

    # 上4：BUS 14 上的工厂负荷运行状态
    ax = axes[3]
    factory_df = prof_df[prof_df["load"].str.contains("工厂", na=False)]
    if len(factory_df) > 0:
        for name, sub in factory_df.groupby("load"):
            ax.fill_between(sub["t"], 0, sub["state"], alpha=0.4, label=name)
            ax.step(sub["t"], sub["state"], where="post", lw=1.2)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("运行状态")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["停机", "运行"])
    ax.set_title("工厂负荷随机启停时间线")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(-0.1, 1.3)

    # 事件竖线（标到所有子图）
    for ev_t in (30, 60, 180):
        for a in axes:
            a.axvline(ev_t, color="purple", ls=":", lw=0.5, alpha=0.4)

    plt.tight_layout()
    out = "lab_scripts/exp06_realistic_loads.png"
    plt.savefig(out, dpi=120)
    print(f"\n图已保存到 {out}")


if __name__ == "__main__":
    main()
