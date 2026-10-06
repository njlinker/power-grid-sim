# -*- coding: utf-8 -*-
"""
Plotly 仪表盘构建器（Phase 5）
================================================
提供一组函数把仿真结果（DataFrame + grid）转成 Plotly Figure：

  build_topology_figure(grid, snapshot_row, ...)
      单时刻的拓扑图（节点电压着色 + 支路载流着色）

  build_timeseries_figure(df, events, ...)
      多面板时序图（电压 / 载流 / 出力 / 损耗）

  build_summary_cards(metrics)
      关键指标卡片（HTML）

输出组合 HTML 用 `assemble_dashboard()`。

依赖：plotly >= 5.0
"""

from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd

import plotly.graph_objects as go
from plotly.subplots import make_subplots

import VeraGridEngine as vg


# ============================================================ 节点坐标（IEEE 14 hardcoded）
# 真实 IEEE 14 大致地理位置（来自 PSS/E 教材）
IEEE14_COORDS = {
    "BUS 1":  (0.0,  4.0),
    "BUS 2":  (1.0,  4.0),
    "BUS 3":  (2.0,  4.0),
    "BUS 4":  (3.0,  3.0),
    "BUS 5":  (2.0,  2.0),
    "BUS 6":  (1.5,  2.5),
    "BUS 7":  (2.0,  1.0),
    "BUS 8":  (2.5,  1.5),
    "BUS 9":  (3.0,  2.0),
    "BUS 10": (4.0,  3.0),
    "BUS 11": (4.5,  2.5),
    "BUS 12": (4.0,  1.5),
    "BUS 13": (4.5,  1.5),
    "BUS 14": (5.0,  2.0),
}

RADIAL5_COORDS = {
    "SRC":  (0.0, 1.0),
    "F1A":  (1.0, 2.0),
    "F1B":  (2.0, 2.5),
    "F2A":  (1.0, 0.0),
    "F2B":  (2.0, -0.5),
}


def get_coords(grid) -> dict[str, tuple[float, float]]:
    """根据电网名猜测坐标集。"""
    bus_names = {b.name for b in grid.buses}
    if {"BUS 1", "BUS 14"}.issubset(bus_names):
        return {k: v for k, v in IEEE14_COORDS.items() if k in bus_names}
    if {"SRC", "F1B"}.issubset(bus_names):
        return {k: v for k, v in RADIAL5_COORDS.items() if k in bus_names}
    # 退化：环形布局
    coords = {}
    n = len(grid.buses)
    for i, b in enumerate(grid.buses):
        angle = 2 * np.pi * i / max(n, 1)
        coords[b.name] = (np.cos(angle), np.sin(angle))
    return coords


# ============================================================ 拓扑图
def build_topology_figure(grid, t: float | None = None,
                          snapshot: dict | None = None,
                          coords: Optional[dict] = None,
                          title: str = "电网拓扑",
                          height: int = 500) -> go.Figure:
    """构建某一时刻的拓扑图。

    Parameters
    ----------
    grid : VeraGrid grid
    t : 时间标签（仅用于标题）
    snapshot : 状态字典（含 v_<bus>, line_<name>），若 None 则画静态结构
    coords : {bus_name: (x, y)}，若 None 用 get_coords()
    """
    if coords is None:
        coords = get_coords(grid)

    fig = go.Figure()

    # 1. 线路（按 loading 着色）
    for ln in grid.lines:
        x0, y0 = coords.get(ln.bus_from.name, (0, 0))
        x1, y1 = coords.get(ln.bus_to.name, (0, 0))
        # 颜色
        if snapshot:
            load = snapshot.get(f"line_{ln.name}", 0)
            if load is None or np.isnan(load):
                color, width = "lightgray", 1
            elif load > 100:
                color, width = "red", 3
            elif load > 80:
                color, width = "orange", 2.5
            else:
                color, width = "green", 2
        else:
            color, width = "lightblue", 1.5
        fig.add_trace(go.Scatter(
            x=[x0, x1], y=[y0, y1],
            mode="lines",
            line=dict(color=color, width=width),
            name=ln.name,
            hovertemplate=f"<b>{ln.name}</b><br>"
                          f"{ln.bus_from.name} → {ln.bus_to.name}<br>"
                          f"loading: {snapshot.get(f'line_{ln.name}', 0) if snapshot else 'n/a'}%"
                          f"<extra></extra>",
            showlegend=False,
        ))

    # 2. 母线（按电压着色）
    bus_x, bus_y, bus_text, bus_color, bus_size = [], [], [], [], []
    for b in grid.buses:
        x, y = coords.get(b.name, (0, 0))
        bus_x.append(x); bus_y.append(y); bus_text.append(b.name)
        # 颜色
        if snapshot:
            v = snapshot.get(f"v_{b.name}", 1.0)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                color = "black"  # 失电
            elif v < 0.95:
                color = "red"
            elif v > 1.05:
                color = "orange"
            else:
                color = "green"
        else:
            color = "lightblue"
        bus_color.append(color)
        # 大小（slack 稍大）
        bus_size.append(18 if getattr(b, "is_slack", False) else 12)

    fig.add_trace(go.Scatter(
        x=bus_x, y=bus_y,
        mode="markers+text",
        marker=dict(size=bus_size, color=bus_color,
                    line=dict(width=2, color="black")),
        text=bus_text, textposition="top center",
        textfont=dict(size=10),
        name="母线",
        hovertemplate="<b>%{text}</b><br>"
                      f"V: {snapshot.get(f'v_%{{text}}', 'n/a') if snapshot else 'n/a'}"
                      "<extra></extra>",
        showlegend=False,
    ))

    title_full = title if t is None else f"{title} (t={t:.1f}s)"
    fig.update_layout(
        title=title_full,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   scaleanchor="x", scaleratio=1),
        plot_bgcolor="white",
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        annotations=[
            dict(x=0.02, y=0.98, xref="paper", yref="paper",
                 text="● 母线电压：<span style='color:green'>●</span> 正常 "
                      "<span style='color:orange'>●</span> 过压 "
                      "<span style='color:red'>●</span> 低压 "
                      "<span style='color:black'>●</span> 失电",
                 showarrow=False, font=dict(size=10), align="left"),
            dict(x=0.98, y=0.02, xref="paper", yref="paper",
                 text="线路 loading：<span style='color:green'>━</span> <80% "
                      "<span style='color:orange'>━</span> 80-100% "
                      "<span style='color:red'>━</span> >100%",
                 showarrow=False, font=dict(size=10), align="right"),
        ],
    )
    return fig


# ============================================================ 时序图
def build_timeseries_figure(df: pd.DataFrame, events: list[tuple[float, str]] | None = None,
                            buses: list[str] | None = None,
                            lines: list[str] | None = None,
                            height: int = 700) -> go.Figure:
    """构建 4 子图时序图：电压 / 载流 / 出力 / 损耗。"""
    if buses is None:
        buses = sorted([c[2:] for c in df.columns if c.startswith("v_")])
    if lines is None:
        lines = sorted([c[5:] for c in df.columns if c.startswith("line_")])

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=("节点电压", "线路载流", "发电机出力", "总有功损耗"),
    )

    # 1. 电压
    for b in buses:
        col = f"v_{b}"
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["t"], y=df[col], name=b, mode="lines",
                hovertemplate=f"<b>{b}</b><br>t=%{{x:.1f}}s<br>V=%{{y:.4f}}<extra></extra>",
            ), row=1, col=1)
    fig.add_hline(y=1.05, line_dash="dash", line_color="red", line_width=0.8,
                  annotation_text="上限 1.05", row=1, col=1)
    fig.add_hline(y=0.95, line_dash="dash", line_color="red", line_width=0.8,
                  annotation_text="下限 0.95", row=1, col=1)

    # 2. 载流
    for ln in lines:
        col = f"line_{ln}"
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["t"], y=df[col], name=ln, mode="lines",
                hovertemplate=f"<b>{ln}</b><br>t=%{{x:.1f}}s<br>loading=%{{y:.1f}}%<extra></extra>",
            ), row=2, col=1)
    fig.add_hline(y=100, line_dash="dash", line_color="red", line_width=0.8,
                  annotation_text="100% 热稳定", row=2, col=1)

    # 3. 发电机出力
    gens = sorted([c[4:] for c in df.columns if c.startswith("gen_")])
    for g in gens:
        col = f"gen_{g}"
        if col in df.columns:
            fig.add_trace(go.Scatter(
                x=df["t"], y=df[col], name=g, mode="lines+markers",
                marker=dict(size=3),
                hovertemplate=f"<b>{g}</b><br>t=%{{x:.1f}}s<br>P=%{{y:.1f}}MW<extra></extra>",
            ), row=3, col=1)

    # 4. 损耗
    if "loss_mw" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["t"], y=df["loss_mw"], name="损耗", mode="lines",
            line=dict(color="purple", width=2),
            hovertemplate="t=%{x:.1f}s<br>loss=%{y:.2f}MW<extra></extra>",
        ), row=4, col=1)

    # 事件竖线（所有子图）
    if events:
        for t, label in events:
            for r in (1, 2, 3, 4):
                fig.add_vline(x=t, line_dash="dot", line_color="gray",
                              line_width=0.8, row=r, col=1)
            fig.add_annotation(x=t, y=1.05, xref=f"x", yref="paper",
                               text=f"⏐ {label}", showarrow=False,
                               font=dict(size=9, color="gray"),
                               xanchor="left")

    fig.update_yaxes(title_text="V (pu)", row=1, col=1)
    fig.update_yaxes(title_text="Loading (%)", row=2, col=1)
    fig.update_yaxes(title_text="P (MW)", row=3, col=1)
    fig.update_yaxes(title_text="Loss (MW)", row=4, col=1)
    fig.update_xaxes(title_text="t (s)", row=4, col=1)

    fig.update_layout(
        title="仿真时序曲线（hover 查看精确值，legend 点击可切换显示）",
        height=height,
        hovermode="x unified",
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02,
                    font=dict(size=8)),
        margin=dict(l=60, r=150, t=60, b=40),
    )
    return fig


# ============================================================ HTML 装配
def assemble_dashboard(topology_fig: go.Figure, ts_fig: go.Figure,
                       metrics: dict, event_log: list[tuple],
                       rule_log: list[tuple],
                       output_path: str):
    """把多个 Plotly 图拼成单 HTML。"""
    # 指标卡片
    def card(label, value, color="blue"):
        return f"""
        <div style="display:inline-block; min-width:160px; padding:12px 18px;
                    margin:6px; border-radius:8px; background:#f5f5f5;
                    border-left:4px solid {color};">
            <div style="font-size:12px; color:#666;">{label}</div>
            <div style="font-size:22px; font-weight:bold; color:#222;">{value}</div>
        </div>"""

    cards_html = "".join([
        card("总步数", metrics.get("n_total", "-"), "gray"),
        card("收敛步数", metrics.get("n_conv", "-"), "green"),
        card("最低电压", f"{metrics.get('min_v', 0):.4f} pu",
             "red" if metrics.get("min_v", 0) < 0.95 else "green"),
        card("最大载流", f"{metrics.get('max_load', 0):.1f}%",
             "red" if metrics.get("max_load", 0) > 100 else "green"),
        card("最大损耗", f"{metrics.get('max_loss', 0):.2f} MW", "orange"),
        card("失电时长", f"{metrics.get('blackout_steps', 0)} 步",
             "red" if metrics.get("blackout_steps", 0) > 0 else "green"),
        card("切负荷量", f"{metrics.get('shed_mw', 0):.2f} MW", "orange"),
        card("规则触发", f"{metrics.get('fire_count', 0)} 次", "blue"),
    ])

    # 事件日志表
    def table(rows, headers):
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
.col {{ flex: 1; min-width: 380px; }}
</style>
</head>
<body>

<h1>⚡ 电网事件驱动仿真仪表盘 (Phase 5)</h1>
<p style="color:#666; margin-top:4px;">
交互式可视化：hover 查看精确值，legend 点击切换显示，框选缩放
</p>

<h2>关键指标</h2>
<div class="panel">{cards_html}</div>

<div class="row">
  <div class="col">
    <h2>实时拓扑</h2>
    <div class="panel" id="topology-div"></div>
  </div>
  <div class="col">
    <h2>时序曲线</h2>
    <div class="panel" id="timeseries-div"></div>
  </div>
</div>

<h2>事件日志 ({len(event_rows)} 条)</h2>
<div class="panel">{table(event_rows, ['时间 (s)', '事件类型', '目标'])}</div>

<h2>规则触发日志 ({len(rule_rows)} 条)</h2>
<div class="panel">{table(rule_rows, ['时间 (s)', '规则 ID', '动作描述'])}</div>

<script>
var topoFig = {topology_fig.to_json()};
var tsFig = {ts_fig.to_json()};
Plotly.newPlot('topology-div', topoFig.data, topoFig.layout, {{responsive: true}});
Plotly.newPlot('timeseries-div', tsFig.data, tsFig.layout, {{responsive: true}});
</script>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"仪表盘已保存到 {output_path}")


def build_topology_animation(grid, df: pd.DataFrame,
                              coords: Optional[dict] = None,
                              key_buses: list[str] | None = None,
                              key_lines: list[str] | None = None,
                              title: str = "电网拓扑（演化）",
                              height: int = 500,
                              n_frames: int = 30) -> go.Figure:
    """构建拓扑演化动画（按时间步）。"""
    if coords is None:
        coords = get_coords(grid)
    if key_buses is None:
        key_buses = [b.name for b in grid.buses]
    if key_lines is None:
        key_lines = [ln.name for ln in grid.lines]

    # 抽帧
    if len(df) > n_frames:
        idx = np.linspace(0, len(df) - 1, n_frames).astype(int)
        sampled = df.iloc[idx]
    else:
        sampled = df

    frames = []
    for _, row in sampled.iterrows():
        snap = row.to_dict()
        t = snap.get("t", 0)
        frame_traces = []

        # 线路
        for ln in grid.lines:
            x0, y0 = coords.get(ln.bus_from.name, (0, 0))
            x1, y1 = coords.get(ln.bus_to.name, (0, 0))
            load = snap.get(f"line_{ln.name}", 0)
            if load is None or (isinstance(load, float) and np.isnan(load)):
                color, w = "lightgray", 1
            elif load > 100:
                color, w = "red", 3
            elif load > 80:
                color, w = "orange", 2.5
            else:
                color, w = "green", 2
            frame_traces.append(go.Scatter(
                x=[x0, x1], y=[y0, y1], mode="lines",
                line=dict(color=color, width=w),
                hovertemplate=f"<b>{ln.name}</b><br>loading={load:.1f}%<extra></extra>",
                showlegend=False,
            ))

        # 母线
        bx, by, bt, bc = [], [], [], []
        for b in grid.buses:
            x, y = coords.get(b.name, (0, 0))
            bx.append(x); by.append(y); bt.append(b.name)
            v = snap.get(f"v_{b.name}", 1.0)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                bc.append("black")
            elif v < 0.95:
                bc.append("red")
            elif v > 1.05:
                bc.append("orange")
            else:
                bc.append("green")
        frame_traces.append(go.Scatter(
            x=bx, y=by, mode="markers+text",
            marker=dict(size=14, color=bc, line=dict(width=2, color="black")),
            text=bt, textposition="top center", textfont=dict(size=10),
            showlegend=False,
            hovertemplate="<b>%{text}</b><extra></extra>",
        ))

        frames.append(go.Frame(data=frame_traces, name=f"t={t:.1f}"))

    # 初始帧（取 t=0）
    initial = sampled.iloc[0].to_dict()
    init_traces = frames[0].data if frames else []

    fig = go.Figure(data=init_traces, frames=frames)
    fig.update_layout(
        title=title,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   scaleanchor="x", scaleratio=1),
        plot_bgcolor="white",
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        updatemenus=[dict(
            type="buttons", showactive=False, y=1.1, x=0.0, xanchor="left",
            buttons=[
                dict(label="▶ 播放", method="animate",
                     args=[None, dict(frame=dict(duration=300, redraw=True),
                                     fromcurrent=True, mode="immediate")]),
                dict(label="⏸ 暂停", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        mode="immediate")]),
            ],
        )],
        sliders=[dict(
            active=0, yanchor="top", y=-0.05, xanchor="left", x=0.0,
            currentvalue=dict(prefix="t=", suffix="s", font=dict(size=12)),
            steps=[dict(args=[[f.name], dict(mode="immediate",
                                              frame=dict(duration=0, redraw=True))],
                        label=f.name, method="animate") for f in frames],
        )] if frames else [],
    )
    return fig
