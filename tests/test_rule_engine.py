"""测试 rule_engine 模块。"""
import pytest

from rule_engine import Rule, RuleEngine, build_default_rules, build_reconfigure_rule
from rule_engine import FaultTracker, shed_load_fraction, reduce_gen_fraction
from event_sim import Simulator, make_schedule
from radial_feeder import build_radial_feeder, LN_S01, LN_TIE, BUS_F1B


class TestRuleDataclass:
    def test_create_rule(self):
        def when(s, g): return False
        def then(g, s): return "noop"
        r = Rule(id="R1", description="test", when=when, then=then)
        assert r.id == "R1"
        assert r.cooldown_s == 0.0
        assert r.fire_count == 0


class TestRuleEngine:
    def test_engine_evaluate_no_fire(self):
        r = Rule(id="R1", description="d", when=lambda s, g: False, then=lambda g, s: "x")
        engine = RuleEngine([r])
        fired = engine.evaluate(None, {"a": 1}, t=0.0)
        assert fired == []
        assert r.fire_count == 0

    def test_engine_evaluate_fire(self):
        r = Rule(id="R1", description="d",
                when=lambda s, g: True,
                then=lambda g, s: "fired!")
        engine = RuleEngine([r])
        fired = engine.evaluate(None, {"a": 1}, t=0.0)
        assert len(fired) == 1
        assert r.fire_count == 1
        assert engine.log[-1][2] == "fired!"

    def test_engine_cooldown(self):
        call_count = [0]
        def when(s, g):
            call_count[0] += 1
            return True
        r = Rule(id="R1", description="d", when=when, then=lambda g, s: "x",
                cooldown_s=10.0)
        engine = RuleEngine([r])
        # t=0 fire
        engine.evaluate(None, {}, t=0.0)
        # t=1 should NOT fire (cooldown 10s)
        fired = engine.evaluate(None, {}, t=1.0)
        assert fired == []
        # t=11 should fire
        fired = engine.evaluate(None, {}, t=11.0)
        assert len(fired) == 1

    def test_disabled_rule(self):
        r = Rule(id="R1", description="d", when=lambda s, g: True,
                then=lambda g, s: "x", enabled=False)
        engine = RuleEngine([r])
        fired = engine.evaluate(None, {}, t=0.0)
        assert fired == []


class TestDefaultRules:
    def test_build_default_rules_returns_3(self):
        rules = build_default_rules()
        assert len(rules) == 3
        ids = {r.id for r in rules}
        assert ids == {"R001_UVLS", "R002_OVGR", "R003_OVERLOAD"}


class TestReconfigureRule:
    def test_build_reconfigure_rule_default(self):
        rule = build_reconfigure_rule()
        assert rule.id == "R004_RECONFIGURE"

    def test_reconfigure_rule_fires_on_blackout(self):
        # S01 跳闸后 F1B 失电，R004 应触发合 TIE
        grid = build_radial_feeder()
        sim = Simulator(grid, dt=1.0)
        rule = build_reconfigure_rule(tie_map={BUS_F1B: LN_TIE, "F2B": LN_TIE})
        engine = RuleEngine([rule])
        sched = make_schedule((5.0, "line_trip", LN_S01))
        df = sim.run(duration=15.0, schedule=sched, rules=engine)
        # F1B 应在 t=6 恢复（黑屏只 1 步）
        assert rule.fire_count >= 1
        f1b_v_after = df[df["t"] >= 6]["v_F1B"].max()
        assert f1b_v_after > 0.8

    def test_fault_tracker(self):
        tracker = FaultTracker(window_s=10.0)
        tracker.record("S01", t=5.0)
        assert len(tracker.events) == 1
        tracker.clear_old(t=20.0)
        assert len(tracker.events) == 0


class TestHelpers:
    def test_shed_load_fraction(self):
        grid = build_radial_feeder()
        before = next(ld for ld in grid.get_loads() if ld.bus.name == BUS_F1B).P
        msg = shed_load_fraction(grid, BUS_F1B, 0.5)
        after = next(ld for ld in grid.get_loads() if ld.bus.name == BUS_F1B and ld.active).P
        assert abs(after - before * 0.5) < 1e-3

    def test_reduce_gen_fraction(self):
        grid = build_radial_feeder()
        gen = next(g for g in grid.get_generators())
        before = gen.P
        msg = reduce_gen_fraction(grid, gen.bus.name, 0.2)
        assert abs(gen.P - before * 0.8) < 1e-3 or gen.P == 0.0
