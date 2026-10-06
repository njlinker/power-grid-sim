# -*- coding: utf-8 -*-
"""
拓扑分析器（Phase C）
================================================
为规则引擎提供"自动理解电网拓扑"的能力：

  identify_switches(grid)
      把线路分成分段开关（sectionalizer, 常闭）和联络开关（tie, 常开）

  build_tie_map(grid)
      自动构建 {失电母线: 联络开关名} 映射，
      用于 R004 自动重构规则

  find_path_to_source(grid, bus)
      BFS 从指定母线找一条到 slack 的路径（含所有线路）

  find_adjacent_sectionalizer(grid, faulted_line)
      找出与故障线路"远离 source 那一端"相邻的分段开关，
      用于故障隔离
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import VeraGridEngine as vg


def get_slack_bus(grid) -> Optional[object]:
    """返回 slack 母线对象（假设只有一个）。"""
    for b in grid.buses:
        if getattr(b, "is_slack", False):
            return b
    return None


def get_neighbors(grid, bus) -> list[tuple[object, object]]:
    """返回 (相邻母线, 连线) 的列表。"""
    neighbors = []
    for ln in grid.lines:
        if not ln.active:
            continue
        if ln.bus_from is bus:
            neighbors.append((ln.bus_to, ln))
        elif ln.bus_to is bus:
            neighbors.append((ln.bus_from, ln))
    return neighbors


def find_path_to_source(grid, bus) -> list[object]:
    """BFS 返回从 bus 到 slack 的路径（含线路对象列表）。

    如果有多个路径，返回任意一个最短的。
    若不可达，返回空列表。
    """
    slack = get_slack_bus(grid)
    if slack is None or bus is slack:
        return []

    visited = {id(bus)}
    queue = deque([(bus, [])])

    while queue:
        current, path = queue.popleft()
        for neighbor, line in get_neighbors(grid, current):
            if id(neighbor) in visited:
                continue
            new_path = path + [line]
            if neighbor is slack:
                return new_path
            visited.add(id(neighbor))
            queue.append((neighbor, new_path))
    return []


def identify_switches(grid, threshold_tie: float = 0.5) -> tuple[list[object], list[object]]:
    """把线路分成分段开关（sectionalizer）和联络开关（tie-switch）。

    判据：
      - sectionalizer: 初始 active=True 且 连接两个"非孤立"母线
      - tie-switch:    初始 active=False（默认联络）

    Parameters
    ----------
    threshold_tie : float
        保留参数。未来可基于"线路两端负荷比"判断，但目前简化用 active 标志。
    """
    sectionalizers = []
    tie_switches = []
    for ln in grid.lines:
        if ln.active:
            sectionalizers.append(ln)
        else:
            tie_switches.append(ln)
    return sectionalizers, tie_switches


def build_tie_map(grid) -> dict[str, str]:
    """自动构建 tie_map: {潜在失电母线: 联络开关名}。

    启发式：
      1. 找出所有联络开关（常开的线路）
      2. 对每个联络开关 (bus_a, bus_b)，检查 bus_a 能否通过某条分段线路
         到达一个"无 tie 但有源"的母线区域（说明 bus_a 是下游）
      3. tie_map[bus_a/bus_b] = 该联络开关名

    简化版（v1）：
      - 把每个 tie 的两端都加入 tie_map
      - 调用方需自行挑选"该触发哪个 tie"
    """
    _, tie_switches = identify_switches(grid)
    tie_map = {}
    for tie in tie_switches:
        a, b = tie.bus_from.name, tie.bus_to.name
        tie_map[a] = tie.name
        tie_map[b] = tie.name
    return tie_map


def find_fault_isolation_switch(grid, faulted_line) -> Optional[object]:
    """找出与故障线路相邻、用于隔离的分段开关。

    思路：
      - 故障线路本身 active=False（已跳闸）
      - 找到故障线路的"下游侧"母线（不能到达 slack 的那一端）
      - 从下游侧出发，沿"树状下游路径"找第一个分段开关（即沿故障点
        向负荷侧延伸的第一条 active=True 的线路）
      - 打开它可以把故障段隔离在更小的范围内

    关键：只沿"故障点辐射出去的子树"找，不要乱跨到其他馈线
    """
    slack = get_slack_bus(grid)
    if slack is None or faulted_line is None:
        return None

    # 区分 source 侧和 load 侧
    # 注意：find_path_to_source 对 slack 自身返回 []，所以要单独处理
    def can_reach_slack(bus):
        return bus is slack or bool(find_path_to_source(grid, bus))

    if can_reach_slack(faulted_line.bus_from):
        load_side_bus = faulted_line.bus_to
    else:
        load_side_bus = faulted_line.bus_from

    # 从 load_side_bus 开始，DFS 沿相邻线路找下游分段开关
    # 关键修复：只沿"离开 slack 的方向"找，不绕回 source 侧
    visited = {id(load_side_bus)}
    stack = [(load_side_bus, None)]
    while stack:
        bus, came_from = stack.pop()
        for neighbor, line in get_neighbors(grid, bus):
            if line is faulted_line:
                continue  # 不要回到故障线路
            if id(neighbor) in visited:
                continue
            # 如果这是分段开关（active=True），且不在故障路径上
            # —— 它是隔离的候选（打开它可以切断下游子树）
            if line.active and line is not faulted_line:
                return line
            visited.add(id(neighbor))
            stack.append((neighbor, line))
    return None


# ============================================================ 健康检查
def describe_topology(grid) -> str:
    """返回拓扑分析的人类可读描述。"""
    lines = []
    sectionalizers, tie_switches = identify_switches(grid)
    lines.append(f"电网: {grid.name}")
    lines.append(f"  分段开关 (常闭, {len(sectionalizers)}): "
                 + ", ".join(ln.name for ln in sectionalizers))
    lines.append(f"  联络开关 (常开, {len(tie_switches)}): "
                 + ", ".join(ln.name for ln in tie_switches))

    tie_map = build_tie_map(grid)
    lines.append(f"  自动 tie_map ({len(tie_map)} 条):")
    for bus, tie in tie_map.items():
        lines.append(f"    {bus} -> {tie}")

    # 路径示例
    slack = get_slack_bus(grid)
    if slack:
        lines.append(f"  示例路径: {slack.name} -> BUS 5 = "
                     + " -> ".join(ln.name for ln in find_path_to_source(grid, _find_bus(grid, "BUS 5"))))
    return "\n".join(lines)


def _find_bus(grid, name):
    for b in grid.buses:
        if b.name == name:
            return b
    return None


if __name__ == "__main__":
    from radial_feeder import build_radial_feeder
    print(describe_topology(build_radial_feeder()))
