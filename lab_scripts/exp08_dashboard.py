# -*- coding: utf-8 -*-
"""
实验八：实时仪表盘（Phase 5 验证）
================================================
目标：生成可交互的 HTML 仪表盘（无需服务器，单文件）

场景：IEEE 14 上跑一个完整剧本：
  - 基线
  - t=10s  BUS 14 +50MW
  - t=25s  BUS 9  +30MW
  - t=40s  G2 跳机
  - t=55s  线 2-4 跳闸
  - t=70s  BUS 14 -50MW
  配合 R001/R002/R003 + R004 规则

输出：
  lab_scripts/exp08_dashboard.html
    包含：
      - 8 个关键指标卡片
      - 拓扑图（着色按当前状态）
      - 拓扑动画（按时间步播放）
      - 4 子图时序曲线
      - 事件日志表
      - 规则触发日志表

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp08_dashboard.py
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import VeraGridEngine as vg

from event_sim import Simulator, make_schedule
from rule_engine import build_default_rules, build_reconfigure_rule, RuleEngine
from dashboard import (
    build_topology_figure, build_topology_animation,
    build_timeseries_figure, assemble_dashboard,
    get_coords,
)


GRID_FILE = "Grids_and_profiles/grids/IEEE 14 bus.raw"


def main():
    grid = vg.open_file(GRID_FILE)
    print(f"电网: {len(grid.buses)} 母线, {len(grid.lines)} 线路")

    # 规则：3 条默认 + R004
    default_rules = build_default_rules(
        v_under=0.93, v_over=1.10,
        line_overload_pct=130.0,
        cooldown=5.0,
    )
    # R004 在 IEEE 14 上不太适用（网状拓扑），我们注释掉
    # reconf_rule = build_reconfigure_rule()
    engine = RuleEngine(default_rules, name="phase5")

    schedule = make_schedule(
        (10.0, "load_add",  "BUS 14", 50.0),
        (25.0, "load_add",  "BUS 9",  30.0),
        (40.0, "gen_trip",  "2_1"),
        (55.0, "line_trip", "2_4_1"),
        (70.0, "load_drop", "_evt_1"),
    )

    sim = Simulator(grid, dt=1.0, verbose=False)
    df = sim.run(duration=90.0, schedule=schedule, rules=engine)
    print(f"仿真完成: {len(df)} 步, {int(df['converged'].sum())} 收敛, "
          f"{len(engine.log)} 次规则触发")

    # ---- 关键指标
    conv = df[df["converged"]]
    v_cols = [c for c in conv.columns if c.startswith("v_")]
    line_cols = [c for c in conv.columns if c.startswith("line_")]
    metrics = {
        "n_total": len(df),
        "n_conv": int(conv.shape[0]),
        "min_v": float(conv[v_cols].min().min()) if len(conv) else 0,
        "max_load": float(conv[line_cols].max().max()) if len(conv) else 0,
        "max_loss": float(conv["loss_mw"].max()) if len(conv) else 0,
        "blackout_steps": 0,  # IEEE 14 没有失电母线
        "shed_mw": 0,
        "fire_count": len(engine.log),
    }

    # ---- 拓扑图（取 t=40s —— gen_trip 触发后的状态）
    target_t = 40.0
    target_row = df[df["t"] == target_t]
    if len(target_row) == 0:
        target_row = df.iloc[len(df) // 2]
    snapshot = target_row.iloc[0].to_dict()
    topology_fig = build_topology_figure(
        grid, t=snapshot.get("t", 0),
        snapshot=snapshot,
        title="电网拓扑（t=40s, G2 跳闸后）",
        height=500,
    )

    # ---- 拓扑动画
    anim_fig = build_topology_animation(
        grid, df,
        title="电网拓扑演化（播放/拖动滑块）",
        height=500, n_frames=40,
    )

    # ---- 时序图
    event_pairs = [(ev.t, ev.kind) for ev in schedule]
    ts_fig = build_timeseries_figure(
        df, events=event_pairs,
        buses=["BUS 1", "BUS 2", "BUS 4", "BUS 9", "BUS 14"],
        lines=["1_2_1", "2_4_1", "2_5_1", "4_5_1"],
        height=700,
    )

    # ---- 事件/规则日志
    event_log = [(ev.t, ev.kind, ev.target) for ev in schedule]
    rule_log = engine.log

    # ---- 拼装 HTML（含拓扑动画 + 时序 + 静态拓扑）
    output = "lab_scripts/exp08_dashboard.html"

    cards = "".join([
        _card("总步数", metrics["n_total"], "gray"),
        _card("收敛步数", metrics["n_conv"], "green"),
        _card("最低电压", f"{metrics['min_v']:.4f} pu",
              "red" if metrics['min_v'] < 0.95 else "green"),
        _card("最大载流", f"{metrics['max_load']:.1f}%",
              "red" if metrics['max_load'] > 100 else "green"),
        _card("最大损耗", f"{metrics['max_loss']:.2f} MW", "orange"),
        _card("规则触发", f"{metrics['fire_count']} 次", "blue"),
    ])

    def _table(rows, headers):
        th = "".join(f"<th style='padding:6px 12px; background:#ddd;'>{h}</th>" for h in headers)
        body = ""
        for r in rows:
            cells = "".join(f"<td style='padding:4px 12px; border-bottom:1px solid #eee;'>{c}</td>" for c in r)
            body += f"<tr>{cells}</tr>"
        return f"<table style='border-collapse:collapse; width:100%; font-size:13px;'><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"

    event_rows = [(f"{t:.1f}", kind, target) for t, kind, target in event_log]
    rule_rows = [(f"{t:.1f}", rid, msg) for t, rid, msg in rule_log]

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>电网仿真仪表盘 - Phase 5</title>
<script src="https://cdn.plot.ly/plotly-3.0.0.min.js"></script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Microsoft YaHei", sans-serif;
       margin: 0; padding: 20px; background: #fafafa; color: #222; }}
h1 {{ margin: 0 0 12px 0; }}
h2 {{ border-left: 4px solid #1976d2; padding-left: 8px; margin-top: 30px; }}
.panel {{ background: white; border-radius: 8px; padding: 16px;
          margin: 12px 0; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
.row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
.col {{ flex: 1; min-width: 420px; }}
.fig-title {{ font-size: 13px; color: #555; margin-bottom: 6px; }}
</style>
</head>
<body>

<h1>⚡ 电网事件驱动仿真仪表盘 (Phase 5)</h1>
<p style="color:#666; margin-top:4px;">
交互式可视化：hover 查看精确值，legend 点击切换显示，框选缩放
</p>

<h2>关键指标</h2>
<div class="panel">{cards}</div>

<div class="row">
  <div class="col">
    <h2>拓扑动画</h2>
    <div class="fig-title">▶ 播放按钮可启动时间演化，拖动滑块跳转特定时刻</div>
    <div class="panel" id="anim-div"></div>
  </div>
  <div class="col">
    <h2>时序曲线</h2>
    <div class="fig-title">4 子图：节点电压 / 线路载流 / 发电机出力 / 总损耗</div>
    <div class="panel" id="ts-div"></div>
  </div>
</div>

<h2>事件日志 ({len(event_rows)} 条)</h2>
<div class="panel">{_table(event_rows, ['时间 (s)', '事件类型', '目标'])}</div>

<h2>规则触发日志 ({len(rule_rows)} 条)</h2>
<div class="panel">{_table(rule_rows, ['时间 (s)', '规则 ID', '动作描述'])}</div>

<script>
var animFig = {anim_fig.to_json()};
var tsFig = {ts_fig.to_json()};
Plotly.newPlot('anim-div', animFig.data, animFig.layout, {{responsive: true}});
Plotly.newPlot('ts-div', tsFig.data, tsFig.layout, {{responsive: true}});
</script>

</body>
</html>"""

    with open(output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n仪表盘已保存到 {output}")
    print(f"  用浏览器打开即可查看（无需服务器）")


def _card(label, value, color="blue"):
    return f"""
    <div style="display:inline-block; min-width:160px; padding:12px 18px;
                margin:6px; border-radius:8px; background:#f5f5f5;
                border-left:4px solid {color};">
        <div style="font-size:12px; color:#666;">{label}</div>
        <div style="font-size:22px; font-weight:bold; color:#222;">{value}</div>
    </div>"""


if __name__ == "__main__":
    main()
