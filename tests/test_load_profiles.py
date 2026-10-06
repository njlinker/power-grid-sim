"""测试 load_profiles 模块。"""
import numpy as np
import pytest

from load_profiles import (
    LoadProfile, LoadProfiler,
    industrial_factory, vfd_load, residential,
)
from event_sim import Simulator
from radial_feeder import build_radial_feeder, BUS_F1B


# BUS_F1B 是 "F1B"，label 格式是 "{bus}@{base_p}MW"
LBL = f"{BUS_F1B}@10.0MW"


class TestLoadProfile:
    def test_create(self):
        p = LoadProfile(bus_name="B1", base_p=10.0, base_q=2.0)
        assert p.bus_name == "B1"
        assert p.base_p == 10.0

    def test_invalid_zip_raises(self):
        with pytest.raises(ValueError):
            LoadProfile(bus_name="B1", base_p=10.0, zip_z=-0.1)


class TestLoadProfiler:
    def test_basic_tick(self):
        grid = build_radial_feeder()
        prof = LoadProfile(bus_name=BUS_F1B, base_p=10.0, base_q=2.0)
        profiler = LoadProfiler(profiles=[prof], seed=42)
        snap = profiler.tick(grid, t=0.0, dt=1.0)
        assert LBL in snap
        assert snap[LBL]["P"] > 0
        assert snap[LBL]["state"] == 1

    def test_state_machine(self):
        """测试启停概率。"""
        grid = build_radial_feeder()
        # 高概率停机
        prof = LoadProfile(
            bus_name=BUS_F1B, base_p=10.0,
            switch_off_prob=1.0,  # 每步必停
            switch_on_prob=0.0,
        )
        profiler = LoadProfiler(profiles=[prof], seed=42)
        profiler.tick(grid, t=0.0, dt=1.0)
        snap1 = profiler.tick(grid, t=1.0, dt=1.0)
        assert snap1[LBL]["state"] == 0

    def test_flicker_modulation(self):
        grid = build_radial_feeder()
        prof = LoadProfile(
            bus_name=BUS_F1B, base_p=10.0,
            flicker_amp=0.5, flicker_freq=1.0,  # 大幅度闪烁
        )
        profiler = LoadProfiler(profiles=[prof], seed=42)
        # 不同 t 时 P 应不同（因 flicker 是 sin 函数）
        s1 = profiler.tick(grid, t=0.0, dt=1.0)
        s2 = profiler.tick(grid, t=0.25, dt=1.0)  # 1/4 周期
        p1 = s1[LBL]["P"]
        p2 = s2[LBL]["P"]
        assert p1 != p2

    def test_zip_response_to_voltage(self):
        """ZIP 模型应对电压变化有不同响应：恒阻抗下 P ∝ V²。"""
        grid = build_radial_feeder()
        prof = LoadProfile(
            bus_name=BUS_F1B, base_p=10.0,
            zip_z=1.0, zip_i=0.0, zip_p=0.0,  # 纯恒阻抗
        )
        profiler = LoadProfiler(profiles=[prof], seed=42)
        profiler.tick(grid, t=0.0, dt=1.0)
        # V = 1.0 时
        profiler.update_v({BUS_F1B: 1.0})
        profiler.tick(grid, t=1.0, dt=1.0)
        p_at_1pu = profiler._history[-1][LBL]["P"]

        # V = 0.9 时
        profiler.update_v({BUS_F1B: 0.9})
        profiler.tick(grid, t=2.0, dt=1.0)
        p_at_09pu = profiler._history[-1][LBL]["P"]

        # 恒阻抗下：低电压 → 更小的 P（因为 P ∝ V²）
        assert p_at_09pu < p_at_1pu
        assert abs(p_at_09pu - 10.0 * 0.9**2) < 0.5  # 10 * 0.81 = 8.1


class TestTemplates:
    def test_industrial_factory(self):
        p = industrial_factory("B1", base_p=20.0)
        assert p.zip_p == 0.5
        assert p.switch_off_prob > 0

    def test_vfd_load(self):
        p = vfd_load("B1", base_p=15.0)
        assert p.zip_p == 1.0
        assert p.flicker_amp > 0

    def test_residential(self):
        p = residential("B1", base_p=5.0)
        assert p.zip_z == 0.6
