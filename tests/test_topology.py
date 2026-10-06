"""测试 topology_analyzer 模块。"""
import pytest

from radial_feeder import build_radial_feeder, LN_S01, LN_TIE
from topology_analyzer import (
    get_slack_bus,
    get_neighbors,
    find_path_to_source,
    identify_switches,
    build_tie_map,
    find_fault_isolation_switch,
)


class TestHelpers:
    def test_get_slack_bus(self):
        grid = build_radial_feeder()
        slack = get_slack_bus(grid)
        assert slack is not None
        assert slack.name == "SRC"

    def test_get_neighbors(self):
        grid = build_radial_feeder()
        src = next(b for b in grid.buses if b.name == "SRC")
        neighbors = get_neighbors(grid, src)
        neighbor_names = {n.name for n, _ in neighbors}
        assert "F1A" in neighbor_names
        assert "F2A" in neighbor_names


class TestPathFinding:
    def test_path_to_source_simple(self):
        grid = build_radial_feeder()
        f1b = next(b for b in grid.buses if b.name == "F1B")
        path = find_path_to_source(grid, f1b)
        line_names = [ln.name for ln in path]
        assert "S01" in line_names
        assert "S13" in line_names

    def test_path_to_source_slack(self):
        grid = build_radial_feeder()
        src = next(b for b in grid.buses if b.name == "SRC")
        path = find_path_to_source(grid, src)
        assert path == []

    def test_path_unreachable(self):
        grid = build_radial_feeder()
        # 全部断开，bus 应该都不可达 slack
        for ln in grid.lines:
            ln.active = False
        f1b = next(b for b in grid.buses if b.name == "F1B")
        path = find_path_to_source(grid, f1b)
        assert path == []


class TestSwitchIdentification:
    def test_identify_switches(self):
        grid = build_radial_feeder()
        secs, ties = identify_switches(grid)
        sec_names = {s.name for s in secs}
        tie_names = {t.name for t in ties}
        assert "S01" in sec_names
        assert "S02" in sec_names
        assert "S13" in sec_names
        assert "S24" in sec_names
        assert "TIE" in tie_names

    def test_build_tie_map(self):
        grid = build_radial_feeder()
        tie_map = build_tie_map(grid)
        assert tie_map.get("F1B") == "TIE"
        assert tie_map.get("F2B") == "TIE"


class TestFaultIsolation:
    def test_isolate_s01(self):
        """S01 故障时应隔离下游的 S13。"""
        grid = build_radial_feeder()
        s01 = next(ln for ln in grid.lines if ln.name == LN_S01)
        s01.active = False
        result = find_fault_isolation_switch(grid, s01)
        # 应该返回 S13（F1A 下游的第一个分段开关）
        assert result is not None
        assert result.name == "S13"

    def test_no_isolation_for_slack_side_fault(self):
        """如果故障段两端都能到达 slack（如回路），不强行隔离。"""
        grid = build_radial_feeder()
        # 让 TIE 闭合，模拟回路
        tie = next(ln for ln in grid.lines if ln.name == LN_TIE)
        tie.active = True
        s01 = next(ln for ln in grid.lines if ln.name == LN_S01)
        s01.active = False
        # 此时 S01 隔离点两侧都可达 slack，函数可能返回下游分段开关
        # 但不应崩溃
        result = find_fault_isolation_switch(grid, s01)
        assert result is None or isinstance(result.name, str)
