"""测试 rules_loader 模块。"""
import os
import tempfile
import pytest

from rules_loader import (
    parse_spec, load_specs_from_yaml, load_rules_from_yaml,
    load_engine_from_yaml, dump_specs_to_yaml,
)
from rule_generator import RuleSpec
from rule_engine import Rule, RuleEngine


SAMPLE_YAML = """
rules:
  - id: R001_TEST
    description: 测试规则
    family: UVLS
    threshold: 0.93
    target: "*"
    action_param: 0.3
    cooldown_s: 5.0
    enabled: true

  - id: R002_TEST
    description: 禁用的规则
    family: OVGR
    threshold: 1.10
    target: "*"
    action_param: 0.2
    cooldown_s: 5.0
    enabled: false
"""


class TestParseSpec:
    def test_basic(self):
        data = {
            "id": "R1", "family": "UVLS", "threshold": 0.93,
            "target": "*", "action_param": 0.3,
        }
        spec = parse_spec(data)
        assert spec.name == "R1"
        assert spec.family == "UVLS"
        assert spec.action_param == 0.3

    def test_missing_required(self):
        with pytest.raises(ValueError, match="缺少必填字段"):
            parse_spec({"family": "UVLS"})


class TestYamlIO:
    def test_load_specs(self, tmp_path):
        yaml_path = tmp_path / "rules.yaml"
        yaml_path.write_text(SAMPLE_YAML, encoding="utf-8")
        specs = load_specs_from_yaml(str(yaml_path))
        # 跳过 disabled
        assert len(specs) == 1
        assert specs[0].name == "R001_TEST"

    def test_load_rules(self, tmp_path):
        yaml_path = tmp_path / "rules.yaml"
        yaml_path.write_text(SAMPLE_YAML, encoding="utf-8")
        rules = load_rules_from_yaml(str(yaml_path))
        assert len(rules) == 1
        assert rules[0].id == "R001_TEST"
        assert callable(rules[0].when)
        assert callable(rules[0].then)

    def test_load_engine(self, tmp_path):
        yaml_path = tmp_path / "rules.yaml"
        yaml_path.write_text(SAMPLE_YAML, encoding="utf-8")
        engine = load_engine_from_yaml(str(yaml_path))
        assert isinstance(engine, RuleEngine)
        assert len(engine.rules) == 1

    def test_dump_and_reload(self, tmp_path):
        yaml_path = tmp_path / "rules.yaml"
        specs = [
            RuleSpec(name="R1", family="UVLS", threshold=0.93,
                    target="*", action_param=0.3),
        ]
        dump_specs_to_yaml(specs, str(yaml_path), comments_header="test")
        reloaded = load_specs_from_yaml(str(yaml_path))
        assert len(reloaded) == 1
        assert reloaded[0].name == "R1"

    def test_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_specs_from_yaml("nonexistent.yaml")
