# -*- coding: utf-8 -*-
"""
实验四：规则引擎 v1 验证（Phase 3）
================================================
目标：对比"无规则" vs "有规则"两个场景，证明规则改善系统指标

事件剧本（与 exp03 相同）：
  t= 10s  BUS 14 +50MW
  t= 25s  BUS 9  +30MW
  t= 40s  G2_1  跳机
  t= 55s  线 2_4_1 跳闸
  t= 70s  BUS 14 -50MW（恢复）

规则组：
  R001_UVLS      V<0.93pu -> 切30%负荷（冷却5s）
  R002_OVGR      V>1.07pu -> 降出力20%（冷却5s）
  R003_OVERLOAD  线 loading>130% -> 末端切10%负荷（冷却5s）

对比指标：
  - 最低电压（越接近 0.95 越好）
  - 最大线路载流百分比（越低越好）
  - 总负荷切除量
  - 规则触发次数

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp04_rule_engine.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 尝试找一个支持中文的字体（Windows 默认 SimHei / Microsoft YaHei）
for candidate in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS"):
    if any(candidate in f.name for f in fm.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [candidate]
        break
plt.rcParams["axes.unicode_minus"] = False  # 负号显示

import VeraGridEngine as vg
from event_sim import Simulator, make_schedule
from rule_engine import build_default_rules, RuleEngine

GRID_FILE = "Grids_and_profiles/grids/IEEE 14 bus.raw"


def build_schedule():
    return make_schedule(
        (10.0, "load_add",  "BUS 14", 50.0),
        (25.0, "load_add",  "BUS 9",  30.0),
        (40.0, "gen_trip",  "2_1"),
        (55.0, "line_trip", "2_4_1"),
        (70.0, "load_drop", "_evt_1"),
    )


def run_scenario(with_rules: bool):
    """跑一次完整剧本，返回 (df, engine or None)。"""
    grid = vg.open_file(GRID_FILE)
    sim = Simulator(grid, dt=1.0, verbose=False)
    schedule = build_schedule()

    engine = None
    if with_rules:
        rules = build_default_rules(
            v_under=0.93,
            v_over=1.10,
            line_overload_pct=130.0,
            shed_fraction_uv=0.30,
            shed_fraction_overload=0.10,
            gen_reduce_fraction=0.20,
            cooldown=5.0,
        )
        engine = RuleEngine(rules, name="default")
    df = sim.run(duration=90.0, schedule=schedule, rules=engine)
    return df, engine


def summarize(df: np.ndarray, label: str) -> dict:
    """从状态 DataFrame 提取关键指标。"""
    conv = df[df["converged"]].copy()
    if len(conv) == 0:
        return {"label": label, "converged_steps": 0}

    # 所有 v_* 列的最小值（最低电压）
    v_cols = [c for c in conv.columns if c.startswith("v_")]
    line_cols = [c for c in conv.columns if c.startswith("line_")]

    min_v = float(conv[v_cols].min().min())
    max_load = float(conv[line_cols].max().max())
    max_loss = float(conv["loss_mw"].max())

    # 总负荷切除量 = 基线 - 当前 (用每个时刻的总负荷近似)
    # 简单做法：gen.P 减少之和（更准的：monitor 每个 step 的 sum(load.P)）
    return {
        "label": label,
        "converged_steps": int(conv.shape[0]),
        "min_v_pu": min_v,
        "max_line_load_pct": max_load,
        "max_loss_mw": max_loss,
    }


def report_summary(rows: list[dict]):
    """打印对比表。"""
    print(f"\n{'场景':<14s} | {'converged':>10s} | {'min V (pu)':>10s} | "
          f"{'max load %':>10s} | {'max loss MW':>10s}")
    print("-" * 70)
    for r in rows:
        print(f"{r['label']:<14s} | {r['converged_steps']:>10d} | "
              f"{r['min_v_pu']:>10.4f} | {r['max_line_load_pct']:>10.2f} | "
              f"{r['max_loss_mw']:>10.2f}")


def plot_comparison(df_off: np.ndarray, df_on: np.ndarray,
                    engine: RuleEngine, key_buses, key_lines):
    """画 6 张子图：电压、线路载流、规则触发时间轴。"""
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), sharex=True)
    fig.suptitle("Phase 3 规则引擎 v1：对比 无规则 vs 有规则", fontsize=13)

    # 上左：无规则 电压
    ax = axes[0, 0]
    for b in key_buses:
        col = f"v_{b}"
        if col in df_off.columns:
            ax.plot(df_off["t"], df_off[col], label=b, lw=1.2)
    ax.axhline(0.95, color="r", ls="--", lw=0.7, alpha=0.5, label="限值 0.95")
    ax.axhline(1.05, color="r", ls="--", lw=0.7, alpha=0.5, label="限值 1.05")
    ax.set_ylim(0.85, 1.15)
    ax.set_ylabel("V (pu)")
    ax.set_title("无规则 — 电压")
    ax.legend(loc="lower left", fontsize=7, ncol=3)
    ax.grid(True, alpha=0.3)

    # 事件竖线（两张电压图共用）
    for ev_t in (10, 25, 40, 55, 70):
        for a in (axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1], axes[2, 0]):
            a.axvline(ev_t, color="gray", ls=":", lw=0.5, alpha=0.4)

    # 上右：有规则 电压
    ax = axes[0, 1]
    for b in key_buses:
        col = f"v_{b}"
        if col in df_on.columns:
            ax.plot(df_on["t"], df_on[col], label=b, lw=1.2)
    ax.axhline(0.95, color="r", ls="--", lw=0.7, alpha=0.5)
    ax.axhline(1.05, color="r", ls="--", lw=0.7, alpha=0.5)
    ax.set_ylim(0.85, 1.15)
    ax.set_ylabel("V (pu)")
    ax.set_title("有规则 — 电压")
    ax.legend(loc="lower left", fontsize=7, ncol=3)
    ax.grid(True, alpha=0.3)

    # 中左：无规则 线路载流
    ax = axes[1, 0]
    for l in key_lines:
        col = f"line_{l}"
        if col in df_off.columns:
            ax.plot(df_off["t"], df_off[col], label=l, lw=1.2)
    ax.axhline(100, color="r", ls="--", lw=0.7, alpha=0.5, label="100%")
    ax.set_ylabel("Loading (%)")
    ax.set_title("无规则 — 线路载流")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)

    # 中右：有规则 线路载流
    ax = axes[1, 1]
    for l in key_lines:
        col = f"line_{l}"
        if col in df_on.columns:
            ax.plot(df_on["t"], df_on[col], label=l, lw=1.2)
    ax.axhline(100, color="r", ls="--", lw=0.7, alpha=0.5, label="100%")
    ax.set_ylabel("Loading (%)")
    ax.set_title("有规则 — 线路载流")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)

    # 下左：有规则 — 发电机出力对比
    ax = axes[2, 0]
    gens = [gen.name for gen in vg.open_file(GRID_FILE).get_generators()]
    for g in gens:
        col = f"gen_{g}"
        if col in df_on.columns:
            ax.plot(df_on["t"], df_on[col], label=g, lw=1.4, marker="o", ms=2)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("P (MW)")
    ax.set_title("有规则 — 发电机出力")
    ax.legend(loc="upper left", fontsize=7, ncol=3)
    ax.grid(True, alpha=0.3)

    # 下右：规则触发时间轴
    ax = axes[2, 1]
    rule_ids = sorted({r_id for _, r_id, _ in engine.log})
    rule_to_y = {rid: i for i, rid in enumerate(rule_ids)}
    color_map = {rid: plt.cm.tab10(i / max(len(rule_ids), 1))
                 for i, rid in enumerate(rule_ids)}
    for t, rid, msg in engine.log:
        ax.scatter(t, rule_to_y[rid], color=color_map[rid], s=80, zorder=3)
    ax.set_xlabel("t (s)")
    ax.set_title(f"规则触发时刻（共 {len(engine.log)} 次）")
    ax.grid(True, alpha=0.3)
    ax.set_yticks(range(len(rule_ids)))
    ax.set_yticklabels(rule_ids)
    ax.set_ylim(-0.5, len(rule_ids) - 0.5)

    plt.tight_layout()
    out_png = "lab_scripts/exp04_rule_engine.png"
    plt.savefig(out_png, dpi=120)
    print(f"\n图已保存到 {out_png}")


def main():
    print("=" * 60)
    print("场景 A: 无规则")
    print("=" * 60)
    df_off, _ = run_scenario(with_rules=False)

    print("\n" + "=" * 60)
    print("场景 B: 有规则")
    print("=" * 60)
    df_on, engine = run_scenario(with_rules=True)

    # 汇总
    sum_off = summarize(df_off, "无规则")
    sum_on = summarize(df_on, "有规则")
    report_summary([sum_off, sum_on])

    # 规则触发明细
    print("\n=== 规则触发明细 ===")
    if engine.log:
        for t, rid, msg in engine.log:
            print(f"  t={t:5.1f}s  {rid:<14s}  {msg}")
    else:
        print("  (无触发)")

    print(f"\n各规则触发次数：")
    for r in engine.rules:
        print(f"  {r.id:<14s}  {r.fire_count} 次")

    # 总负荷切除量（粗略）：t=0 时总线负荷 vs 终点总负荷
    # 需要重新读基线计算，因为 df 没记 load 总和
    base_grid = vg.open_file(GRID_FILE)
    base_total = sum(ld.P for ld in base_grid.get_loads())
    final_grid_state = df_on.iloc[-1]
    print(f"\n基线总负荷: {base_total:.2f} MW")
    print(f"净增负荷（事件）：+80MW → 撤 50MW = +30MW")
    print(f"  → 如果规则不再切负荷，t=90s 时应为 {base_total + 30:.2f} MW")

    # 画图
    key_buses = ["BUS 1", "BUS 2", "BUS 4", "BUS 9", "BUS 14"]
    key_lines = ["2_4_1", "2_5_1", "4_5_1", "1_2_1"]
    plot_comparison(df_off, df_on, engine, key_buses, key_lines)


if __name__ == "__main__":
    main()
