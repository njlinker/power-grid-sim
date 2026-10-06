"""测试 event_sim 模块：Event、inject、Simulator、snapshot。"""
import numpy as np
import pytest

from event_sim import Event, make_schedule, inject, Simulator, reset_load_counter
from event_sim import find_bus, find_generator, find_line, find_load
from radial_feeder import (
    build_radial_feeder, LN_S01, LN_TIE, BUS_F1B, BUS_F2B,
)


class TestEvent:
    def test_create_event(self):
        ev = Event(t=5.0, kind="line_trip", target="S01", magnitude=0.0)
        assert ev.t == 5.0
        assert ev.kind == "line_trip"
        assert ev.target == "S01"

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError, match="未知事件类型"):
            Event(t=0, kind="bad_kind", target="X")

    def test_event_is_frozen(self):
        ev = Event(t=0, kind="line_trip", target="S01")
        with pytest.raises(Exception):  # FrozenInstanceError
            ev.t = 10.0

    def test_make_schedule(self):
        sched = make_schedule(
            (5.0, "load_add", "BUS 14", 50.0),
            (10.0, "gen_trip", "2_1"),
        )
        assert len(sched) == 2
        assert sched[0].kind == "load_add"
        assert sched[1].target == "2_1"


class TestInject:
    def setup_method(self):
        reset_load_counter()  # 每次测试前重置计数器
        self.grid = build_radial_feeder()

    def test_line_trip(self):
        s01 = next(ln for ln in self.grid.lines if ln.name == LN_S01)
        assert s01.active is True
        inject(self.grid, Event(t=0, kind="line_trip", target=LN_S01))
        assert s01.active is False

    def test_line_close(self):
        s01 = next(ln for ln in self.grid.lines if ln.name == LN_S01)
        s01.active = False
        inject(self.grid, Event(t=0, kind="line_close", target=LN_S01))
        assert s01.active is True

    def test_gen_trip(self):
        from radial_feeder import BUS_SRC
        gen = next(g for g in self.grid.get_generators() if g.bus.name == BUS_SRC)
        inject(self.grid, Event(t=0, kind="gen_trip", target=gen.name))
        assert gen.active is False

    def test_load_add_creates_new_load(self):
        before = len(self.grid.get_loads())
        inject(self.grid, Event(t=0, kind="load_add", target=BUS_F1B, magnitude=10.0))
        after = len(self.grid.get_loads())
        assert after == before + 1
        new_load = next(ld for ld in self.grid.get_loads() if ld.name.startswith("_evt_"))
        assert abs(new_load.P - 10.0) < 1e-3

    def test_load_drop(self):
        inject(self.grid, Event(t=0, kind="load_add", target=BUS_F1B, magnitude=10.0))
        evt1 = next(ld for ld in self.grid.get_loads() if ld.name.startswith("_evt_"))
        inject(self.grid, Event(t=0, kind="load_drop", target=evt1.name))
        assert evt1.active is False


class TestSimulator:
    def test_simulator_runs(self):
        grid = build_radial_feeder()
        sim = Simulator(grid, dt=1.0)
        df = sim.run(duration=10.0, schedule=[])
        assert len(df) == 11  # t=0 基线 + 10 步
        assert all(df["converged"])

    def test_simulator_handles_line_trip(self):
        grid = build_radial_feeder()
        sim = Simulator(grid, dt=1.0)
        sched = make_schedule((5.0, "line_trip", LN_S01))
        df = sim.run(duration=15.0, schedule=sched)
        # t=0 基线 + 15 步
        assert len(df) == 16
        assert df.iloc[-1]["converged"]

    def test_reset_load_counter(self):
        # 模拟跨场景的情况
        reset_load_counter()
        from event_sim import _load_counter
        assert _load_counter == 0


class TestSnapshot:
    def test_snapshot_keys_present(self):
        grid = build_radial_feeder()
        sim = Simulator(grid, dt=1.0)
        df = sim.run(duration=5.0)
        # 应该有 v_<bus> 和 line_<name> 列
        v_cols = [c for c in df.columns if c.startswith("v_")]
        line_cols = [c for c in df.columns if c.startswith("line_")]
        sw_cols = [c for c in df.columns if c.startswith("sw_")]
        assert len(v_cols) >= 5  # 5 个母线
        assert len(line_cols) >= 5
        assert len(sw_cols) >= 5
        assert "loss_mw" in df.columns
        assert "converged" in df.columns

    def test_voltages_in_reasonable_range(self):
        grid = build_radial_feeder()
        sim = Simulator(grid, dt=1.0)
        df = sim.run(duration=5.0)
        v_cols = [c for c in df.columns if c.startswith("v_")]
        for c in v_cols:
            assert df[c].min() > 0.85
            assert df[c].max() < 1.15
