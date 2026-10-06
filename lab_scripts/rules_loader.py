# -*- coding: utf-8 -*-
"""
规则库 YAML 加载器（Phase A）
================================================
把 YAML 配置文件解析为可执行 Rule 列表。

YAML 格式：
    rules:
      - id: R001_UVLS
        description: 低压减载
        family: UVLS         # UVLS / OVGR / OVERLOAD / RECONF
        threshold: 0.93
        target: "*"           # "*" = worst bus, 或具体母线名
        action_param: 0.30    # 切负荷比例 / 降出力比例
        cooldown_s: 5.0
        enabled: true

      - id: R004_RECONF
        description: 自动重构
        family: RECONF
        threshold: 0.05       # 失电阈值
        target: TIE           # 联络开关名
        action_param: 0.0
        cooldown_s: 1.0
        enabled: true

使用：
    from rules_loader import load_rules
    rules = load_rules("config/rules.yaml")
    engine = RuleEngine(rules)
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

try:
    import yaml
except ImportError:
    raise ImportError(
        "yaml not installed. Install via: pip install pyyaml"
    )

from rule_engine import Rule, RuleEngine
from rule_generator import RuleSpec, materialize


def parse_spec(data: dict) -> RuleSpec:
    """把单个 YAML dict 转为 RuleSpec。"""
    required = ["family", "threshold", "target", "action_param"]
    for k in required:
        if k not in data:
            raise ValueError(f"规则缺少必填字段 '{k}': {data}")

    return RuleSpec(
        name=data.get("id", data.get("name", "unnamed")),
        family=data["family"],
        threshold=float(data["threshold"]),
        target=str(data["target"]),
        action_param=float(data["action_param"]),
        cooldown_s=float(data.get("cooldown_s", 5.0)),
        description=data.get("description", ""),
    )


def load_specs_from_yaml(path: Union[str, Path]) -> list[RuleSpec]:
    """从 YAML 文件加载 RuleSpec 列表（不实例化）。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"规则文件不存在: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict) or "rules" not in data:
        raise ValueError(f"YAML 顶层必须是 dict 且包含 'rules' 字段")

    specs = []
    for item in data["rules"]:
        if not item.get("enabled", True):
            continue  # 跳过未启用的规则
        specs.append(parse_spec(item))
    return specs


def load_rules_from_yaml(path: Union[str, Path]) -> list[Rule]:
    """从 YAML 加载并实例化为可执行 Rule 列表。"""
    specs = load_specs_from_yaml(path)
    return [materialize(s) for s in specs]


def load_engine_from_yaml(path: Union[str, Path], name: str = "yaml_engine") -> RuleEngine:
    """便捷函数：直接从 YAML 构造 RuleEngine。"""
    rules = load_rules_from_yaml(path)
    return RuleEngine(rules, name=name)


def dump_specs_to_yaml(specs: list[RuleSpec], path: Union[str, Path],
                        comments_header: str = ""):
    """把 RuleSpec 列表写到 YAML 文件（便于模板生成）。"""
    path = Path(path)
    out = {"rules": []}
    for s in specs:
        out["rules"].append({
            "id": s.name,
            "description": s.description,
            "family": s.family,
            "threshold": s.threshold,
            "target": s.target,
            "action_param": s.action_param,
            "cooldown_s": s.cooldown_s,
            "enabled": True,
        })

    with open(path, "w", encoding="utf-8") as f:
        if comments_header:
            f.write(f"# {comments_header}\n")
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False,
                       default_flow_style=False)
