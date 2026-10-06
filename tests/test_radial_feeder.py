"""测试 radial_feeder 模块。"""
import pytest

from radial_feeder import (
    build_radial_feeder,
    LN_S01, LN_S13, LN_S02, LN_S24, LN_TIE,
    BUS_SRC, BUS_F1A, BUS_F1B, BUS_F2A, BUS_F2B,
)
import VeraGridEngine as vg


class TestBuild:
    def test_default_build(self):
        grid = build_radial_feeder()
        assert len(grid.buses) == 5
        assert len(grid.lines) == 5  # 4 分段 + 1 TIE
        # 检查 TIE 默认断开
        tie = next(ln for ln in grid.lines if ln.name == LN_TIE)
        assert tie.active is False
        # 其他默认闭合
        for name in (LN_S01, LN_S13, LN_S02, LN_S24):
            ln = next(l for l in grid.lines if l.name == name)
            assert ln.active is True

    def test_build_with_custom_loads(self):
        grid = build_radial_feeder(load_p=5.0, load_q=2.0)
        total_load = sum(ld.P for ld in grid.get_loads())
        assert abs(total_load - 10.0) < 1e-3

    def test_line_rates_set(self):
        grid = build_radial_feeder(line_rate=42.0)
        for ln in grid.lines:
            assert ln.rate == 42.0

    def test_buses_have_correct_names(self):
        grid = build_radial_feeder()
        names = {b.name for b in grid.buses}
        assert names == {BUS_SRC, BUS_F1A, BUS_F1B, BUS_F2A, BUS_F2B}

    def test_power_flow_converges(self):
        grid = build_radial_feeder()
        pf = vg.power_flow(grid)
        assert pf.converged
