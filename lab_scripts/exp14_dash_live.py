# -*- coding: utf-8 -*-
"""
实验十四：真·实时仪表盘（Dash）
================================================
用 Dash + 间隔回调实现"浏览器实时看仿真在跑"。

工作原理：
  - 后台线程跑 Simulator（按 dt 推进，每步触发事件）
  - 共享一个 history 列表（deque），最多保留 200 步
  - Dash interval 每 1 秒拉一次最新状态，刷新图表

启动：
  gridcal-env/Scripts/python.exe lab_scripts/exp14_dash_live.py
  然后浏览器打开 http://127.0.0.1:8050

停止：Ctrl+C
"""

import warnings
warnings.filterwarnings("ignore")

import threading
import time
from collections import deque
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import dash
from dash import dcc, html
from dash.dependencies import Input, Output

import VeraGridEngine as vg

from event_sim import Simulator, snapshot, make_schedule
from rules_loader import load_engine_from_yaml
from radial_feeder import (
    build_radial_feeder, LN_S01, LN_TIE, LN_S13,
    BUS_SRC, BUS_F1A, BUS_F1B, BUS_F2A, BUS_F2B,
)

RULES_YAML = "lab_scripts/config/rules.yaml"

# ============ 全局状态：仿真历史
HISTORY: deque = deque(maxlen=200)  # 最近 200 步的快照
LATEST_SNAPSHOT: dict = {}
SIM_DONE = False


def simulation_thread():
    """后台线程：跑仿真并把快照推入 HISTORY。"""
    global LATEST_SNAPSHOT, SIM_DONE

    grid = build_radial_feeder()
    engine = load_engine_from_yaml(RULES_YAML, name="live_engine")
    sim = Simulator(grid, dt=1.0, verbose=False)

    # 剧本：S01 跳闸 -> R004 自动恢复 -> S13 跳闸（双重故障）
    schedule = make_schedule(
        (5.0,  "line_trip",  LN_S01),
        (25.0, "line_close", LN_S01),
        (25.0, "line_trip",  LN_TIE),
        (35.0, "line_trip",  LN_S13),  # 双重故障
    )
    df = sim.run(duration=60.0, schedule=schedule, rules=engine)

    # 把仿真结果逐帧推入 HISTORY（按 0.2s/帧，加速播放）
    for _, row in df.iterrows():
        snap = row.to_dict()
        HISTORY.append(snap)
        LATEST_SNAPSHOT = snap
        time.sleep(0.2)

    SIM_DONE = True


# ============ Dash app
app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("⚡ 电网仿真实时仪表盘 (Phase F)"),
    html.Div(id="status-bar", style={"padding": "10px", "background": "#f5f5f5",
                                      "border-radius": "8px", "margin-bottom": "12px"}),
    html.Div([
        html.Div([
            html.H3("实时拓扑"),
            dcc.Graph(id="topology-graph"),
        ], style={"width": "48%", "display": "inline-block"}),
        html.Div([
            html.H3("母线电压"),
            dcc.Graph(id="voltage-graph"),
        ], style={"width": "48%", "display": "inline-block", "float": "right"}),
    ]),
    html.Div([
        html.Div([
            html.H3("线路载流"),
            dcc.Graph(id="loading-graph"),
        ], style={"width": "48%", "display": "inline-block"}),
        html.Div([
            html.H3("规则触发日志"),
            html.Pre(id="rule-log", style={"background": "#fafafa", "padding": "10px",
                                            "maxHeight": "300px", "overflowY": "auto",
                                            "fontSize": "11px"}),
        ], style={"width": "48%", "display": "inline-block", "float": "right"}),
    ]),
    dcc.Interval(id="interval-component", interval=1000, n_intervals=0),
])


def make_topology_fig(snap, grid):
    """生成拓扑图（按快照着色）。"""
    coords = {
        BUS_SRC: (0.0, 1.0),
        BUS_F1A: (1.0, 2.0),
        BUS_F1B: (2.0, 2.5),
        BUS_F2A: (1.0, 0.0),
        BUS_F2B: (2.0, -0.5),
    }
    fig = go.Figure()

    # 线路
    for ln in grid.lines:
        x0, y0 = coords.get(ln.bus_from.name, (0, 0))
        x1, y1 = coords.get(ln.bus_to.name, (0, 0))
        load = snap.get(f"line_{ln.name}", 0) or 0
        if load > 100:
            color, w = "red", 3
        elif load > 80:
            color, w = "orange", 2.5
        else:
            color, w = "green", 2
        fig.add_trace(go.Scatter(
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
        v = snap.get(f"v_{b.name}", 1.0) or 0
        if v < 0.95:
            bc.append("red")
        elif v > 1.05:
            bc.append("orange")
        else:
            bc.append("green")
    fig.add_trace(go.Scatter(
        x=bx, y=by, mode="markers+text",
        marker=dict(size=18, color=bc, line=dict(width=2, color="black")),
        text=bt, textposition="top center",
        showlegend=False,
        hovertemplate="<b>%{text}</b><extra></extra>",
    ))

    fig.update_layout(
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   scaleanchor="x", scaleratio=1),
        plot_bgcolor="white",
        margin=dict(l=20, r=20, t=20, b=20),
        height=350,
    )
    return fig


def make_timeseries_fig(history, prefix, title):
    """生成时序图。"""
    if len(history) == 0:
        return go.Figure().update_layout(title=title)

    fig = go.Figure()
    for key in history[0].keys():
        if key.startswith(prefix):
            vals = [snap.get(key, np.nan) for snap in history]
            ts = [snap.get("t", 0) for snap in history]
            label = key[len(prefix):]
            fig.add_trace(go.Scatter(
                x=ts, y=vals, mode="lines",
                name=label,
                line=dict(width=1.5),
            ))

    if prefix == "v_":
        fig.add_hline(y=0.95, line_dash="dash", line_color="red", line_width=0.7)
        fig.add_hline(y=1.05, line_dash="dash", line_color="red", line_width=0.7)
        fig.update_yaxes(title_text="V (pu)", range=[0.85, 1.15])
    elif prefix == "line_":
        fig.add_hline(y=100, line_dash="dash", line_color="red", line_width=0.7)
        fig.update_yaxes(title_text="Loading (%)")

    fig.update_layout(
        title=title, height=350,
        margin=dict(l=50, r=20, t=40, b=30),
        legend=dict(font=dict(size=9)),
    )
    fig.update_xaxes(title_text="t (s)")
    return fig


# ============ 回调
@app.callback(
    [Output("topology-graph", "figure"),
     Output("voltage-graph", "figure"),
     Output("loading-graph", "figure"),
     Output("rule-log", "children"),
     Output("status-bar", "children")],
    [Input("interval-component", "n_intervals")],
)
def update_dashboard(n):
    if not LATEST_SNAPSHOT or not HISTORY:
        empty = go.Figure()
        return empty, empty, empty, "等待仿真启动...", "初始化中..."

    grid = build_radial_feeder()  # 重建用于 fig（不修改 state）

    topo_fig = make_topology_fig(LATEST_SNAPSHOT, grid)
    v_fig = make_timeseries_fig(list(HISTORY), "v_", "母线电压时序")
    l_fig = make_timeseries_fig(list(HISTORY), "line_", "线路载流时序")

    # 状态栏
    snap = LATEST_SNAPSHOT
    t = snap.get("t", 0)
    v_f1b = snap.get(f"v_{BUS_F1B}", 0) or 0
    tie_sw = snap.get(f"sw_{LN_TIE}", 0) or 0
    s01_sw = snap.get(f"sw_{LN_S01}", 0) or 0
    s13_sw = snap.get(f"sw_{LN_S13}", 0) or 0
    status = (
        f"时间: {t:.1f}s | "
        f"F1B 电压: {v_f1b:.4f} pu | "
        f"S01: {'断开' if not s01_sw else '闭合'} | "
        f"S13: {'断开' if not s13_sw else '闭合'} | "
        f"TIE: {'闭合' if tie_sw else '断开'} | "
        f"已采集 {len(HISTORY)} 帧 | "
        f"{'仿真已结束' if SIM_DONE else '仿真进行中...'}"
    )

    # 规则日志（从 history 中找 rules_fired 标记）
    log_lines = []
    for snap in list(HISTORY)[-30:]:
        fired = snap.get("rules_fired", "")
        if fired:
            log_lines.append(f"t={snap.get('t', 0):.1f}s  {fired}")
    log_text = "\n".join(log_lines) if log_lines else "(暂无触发)"

    return topo_fig, v_fig, l_fig, log_text, status


def main():
    # 启动仿真线程
    t = threading.Thread(target=simulation_thread, daemon=True)
    t.start()

    print("=" * 60)
    print("Dash 实时仪表盘启动中...")
    print("浏览器打开: http://127.0.0.1:8050")
    print("=" * 60)
    app.run(debug=False, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
