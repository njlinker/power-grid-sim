"""测试 rule_generator 模块。"""
import pytest

from rule_generator import (
    RuleSpec, materialize,
    gen_uvls_candidates, gen_overload_candidates, gen_reconf_candidates,
    evaluate_rule, evaluate_compound, Scenario,
)
from radial_feeder import build_radial_feeder, LN_S01, LN_TIE, BUS_F1B


class TestRuleSpec:
    def test_create(self):
        s = RuleSpec(name="R1", family="UVLS", threshold=0.9,
                    target="*", action_param=0.3)
        assert s.name == "R1"
        assert "V<0.9" in s.description

    def test_auto_description(self):
        s = RuleSpec(name="R1", family="OVERLOAD", threshold=130.0,
                    target="*", action_param=0.1)
        assert "loading>130" in s.description


class TestMaterialize:
    def test_uvls_materialize(self):
        s = RuleSpec(name="R1", family="UVLS", threshold=0.9,
                    target="*", action_param=0.3)
        rule = materialize(s)
        assert rule.id == "R1"
        # 测试 when 函数
        assert rule.when({"v_BUS1": 0.85, "v_BUS2": 1.0}, None) is True
        assert rule.when({"v_BUS1": 0.95, "v_BUS2": 1.0}, None) is False

    def test_reconf_materialize(self):
        s = RuleSpec(name="R1", family="RECONF", threshold=0.05,
                    target="TIE", action_param=0.0)
        rule = materialize(s)
        # 没有失电时不触发
        from radial_feeder import build_radial_feeder
        grid = build_radial_feeder()
        assert rule.when({"v_BUS1": 1.0}, grid) is False


class TestCandidateGenerators:
    def test_uvls_candidates(self):
        specs = gen_uvls_candidates(v_thresholds=(0.9, 0.95),
                                    shed_fractions=(0.2, 0.3))
        # 2 thresholds * 2 fractions * 1 target = 4
        assert len(specs) == 4

    def test_overload_candidates(self):
        specs = gen_overload_candidates(load_thresholds=(110.0, 130.0),
                                        shed_fractions=(0.1,))
        # 2 * 1 = 2
        assert len(specs) == 2

    def test_reconf_candidates(self):
        specs = gen_reconf_candidates(tie_switches=("TIE",))
        assert len(specs) == 1
        assert specs[0].family == "RECONF"


class TestEvaluate:
    def _make_scenario(self):
        from event_sim import make_schedule
        from radial_feeder import LN_TIE
        grid_factory = lambda: build_radial_feeder()
        return Scenario(
            name="test",
            duration=20.0,
            schedule=make_schedule((5.0, "line_trip", LN_TIE)),
            grid_factory=grid_factory,
        )

    def test_evaluate_uvls_rule(self):
        scenario = self._make_scenario()
        spec = RuleSpec(name="R1", family="UVLS", threshold=0.5,
                       target="*", action_param=0.3)
        score, metrics = evaluate_rule(spec, scenario)
        assert "min_v" in metrics
        assert "max_load" in metrics
        assert "blackout_steps" in metrics
        assert isinstance(score, float)

    def test_evaluate_compound(self):
        scenario = self._make_scenario()
        specs = [
            RuleSpec(name="R1", family="UVLS", threshold=0.5,
                    target="*", action_param=0.3),
            RuleSpec(name="R2", family="OVERLOAD", threshold=110.0,
                    target="*", action_param=0.1),
        ]
        score, metrics = evaluate_compound(specs, scenario)
        assert "fire_count" in metrics
