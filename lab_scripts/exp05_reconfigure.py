# -*- coding: utf-8 -*-
"""
实验五：配电自动重构（Phase 2 验证）
================================================
目标：在辐射状配电 feeder 上验证自动重构规则 R004_RECONFIGURE

拓扑（5-bus 双馈线 + 联络）：
                SRC
               /  \
             S01  S02            (常闭)
             F1A  F2A
             S13  S24            (常闭)
             F1B  F2B
                TIE              (常开)

事件剧本：
  t=  0s   基线（所有分段闭合，TIE 断开）
  t=  5s   S01 跳闸 -> F1A/F1B 失电
  t= 10s   R004 触发 -> 闭合 TIE -> F1B 经 F2 转供恢复
  t= 30s   恢复正常（闭合 S01 + 断开 TIE）

对比场景：
  - 无规则：S01 跳闸后 F1B 永久失电
  - 有规则：R004 自动闭合 TIE，F1B 在 5s 内恢复

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp05_reconfigure.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# CJK 字体
for cand in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS"):
    if any(cand in f.name for f in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [cand]
        break
plt.rcParams["axes.unicode_minus"] = False

import VeraGridEngine as vg
from event_sim import Simulator, make_schedule
from rule_engine import build_reconfigure_rule, RuleEngine
from radial_feeder import (
    build_radial_feeder, describe,
    BUS_SRC, BUS_F1A, BUS_F1B, BUS_F2A, BUS_F2B,
    LN_S01, LN_S13, LN_S02, LN_S24, LN_TIE,
)


def run_scenario(with_rules: bool):
    grid = build_radial_feeder()
    sim = Simulator(grid, dt=1.0, verbose=False)
    schedule = make_schedule(
        (5.0,  "line_trip",  LN_S01),    # 跳 S01
        (30.0, "line_close", LN_S01),    # 恢复 S01
        (30.0, "line_trip",  LN_TIE),    # 同时断开 TIE（恢复正常）
    )
    engine = None
    if with_rules:
        rule = build_reconfigure_rule(tie_map={BUS_F1B: LN_TIE, BUS_F2B: LN_TIE})
        engine = RuleEngine([rule], name="reconfig")
    df = sim.run(duration=40.0, schedule=schedule, rules=engine)
    return df, engine


def summarize(df, label: str) -> dict:
    conv = df[df["converged"]].copy()
    if len(conv) == 0:
        return {"label": label, "converged_steps": 0}
    v_cols = [c for c in conv.columns if c.startswith("v_")]
    min_v = float(conv[v_cols].min().min())
    # F1B 最低电压
    f1b_min = float(conv["v_F1B"].min())
    # F1B 失电持续时间（V < 0.05）
    blackout_steps = int((conv["v_F1B"] < 0.05).sum())
    return {
        "label": label,
        "converged_steps": int(conv.shape[0]),
        "min_v_pu": min_v,
        "f1b_min_v_pu": f1b_min,
        "f1b_blackout_steps": blackout_steps,
    }


def report(rows):
    print(f"\n{'场景':<14s} | {'conv':>6s} | {'min V (pu)':>10s} | "
          f"{'F1B min V':>10s} | {'F1B 失电步数':>10s}")
    print("-" * 70)
    for r in rows:
        print(f"{r['label']:<14s} | {r['converged_steps']:>6d} | "
              f"{r['min_v_pu']:>10.4f} | {r['f1b_min_v_pu']:>10.4f} | "
              f"{r['f1b_blackout_steps']:>10d}")


def plot_compare(df_off, df_on, engine, key_buses):
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
    fig.suptitle("Phase 2 配电自动重构：对比 无规则 vs 有规则", fontsize=13)

    # 上：无规则 母线电压
    ax = axes[0]
    for b in key_buses:
        col = f"v_{b}"
        if col in df_off.columns:
            ax.plot(df_off["t"], df_off[col], label=b, lw=1.4)
    ax.axhline(0.05, color="r", ls=":", lw=0.7, alpha=0.5, label="失电阈值 0.05")
    ax.set_ylim(-0.05, 1.15)
    ax.set_ylabel("V (pu)")
    ax.set_title("无规则 — F1B 永久失电")
    ax.legend(loc="lower left", fontsize=8, ncol=3)
    ax.grid(True, alpha=0.3)

    # 中：有规则 母线电压
    ax = axes[1]
    for b in key_buses:
        col = f"v_{b}"
        if col in df_on.columns:
            ax.plot(df_on["t"], df_on[col], label=b, lw=1.4)
    ax.axhline(0.05, color="r", ls=":", lw=0.7, alpha=0.5, label="失电阈值 0.05")
    ax.set_ylim(-0.05, 1.15)
    ax.set_ylabel("V (pu)")
    ax.set_title("有规则 — R004 自动闭合 TIE 恢复 F1B")
    ax.legend(loc="lower left", fontsize=8, ncol=3)
    ax.grid(True, alpha=0.3)

    # 下：TIE 开关状态（有规则侧，真实 active 标志）
    ax = axes[2]
    sw_col = f"sw_{LN_TIE}"
    if sw_col in df_on.columns:
        tie_state = df_on[sw_col].fillna(0).astype(int)
        ax.fill_between(df_on["t"], 0, tie_state, alpha=0.4, color="green",
                        label=f"TIE 闭合 (active=True)")
        ax.fill_between(df_on["t"], 1, 2, where=(tie_state == 0),
                        alpha=0.4, color="red", label="TIE 断开 (active=False)")
    for ev_t in (5, 30):
        ax.axvline(ev_t, color="gray", ls="--", lw=0.8)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("TIE 状态")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["断开", "闭合"])
    ax.set_ylim(-0.1, 1.3)
    ax.set_title("TIE 联络开关真实状态（snapshot 记录）")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = "lab_scripts/exp05_reconfigure.png"
    plt.savefig(out, dpi=120)
    print(f"\n图已保存到 {out}")


def main():
    print("=" * 60)
    print("辐射状配电 feeder 描述：")
    print("=" * 60)
    print(describe(build_radial_feeder()))

    print("\n" + "=" * 60)
    print("场景 A: 无规则（S01 跳闸后 F1B 永久失电）")
    print("=" * 60)
    df_off, _ = run_scenario(with_rules=False)

    print("\n" + "=" * 60)
    print("场景 B: 有 R004_RECONFIGURE")
    print("=" * 60)
    df_on, engine = run_scenario(with_rules=True)

    # 规则触发明细
    print("\n=== R004 触发明细 ===")
    if engine.log:
        for t, rid, msg in engine.log:
            print(f"  t={t:5.1f}s  {msg}")
    else:
        print("  (无触发)")

    # 对比指标
    rows = [summarize(df_off, "无规则"),
            summarize(df_on, "有 R004")]
    report(rows)

    # 画图
    plot_compare(df_off, df_on, engine,
                 key_buses=[BUS_F1B, BUS_F2B, BUS_F1A, BUS_F2A])


if __name__ == "__main__":
    main()
