# -*- coding: utf-8 -*-
"""
场景库（Phase B）
================================================
内置一批典型剧本，供基准测试和压力验证使用。

每个 Scenario 包含：
  - name          场景名
  - description   描述
  - grid_factory  () -> grid，每次返回新实例（避免状态污染）
  - schedule      事件列表
  - duration      仿真时长
  - pass_criteria 通过判据（min_v / max_load / blackout_steps 阈值）
  - category      分类（N-1 / N-2 / 负荷 / 故障 / 极限）

典型场景：
  1. ieee14_line1_2_trip        N-1：线路 1-2 跳闸
  2. ieee14_g2_trip             N-1：发电机 2 跳机
  3. ieee14_load_step           阶跃：BUS14 +80MW
  4. ieee14_cascade             级联：先 +负荷 → G2 跳 → 线 2-4 跳
  5. radial_s01_trip            馈线 1 跳闸（R004 验证）
  6. radial_heavy_overload      重负荷 + 馈线跳闸（OVL 验证）
  7. radial_double_fault        双线故障（恢复 + 切负荷验证）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional
import VeraGridEngine as vg

from event_sim import make_schedule
from radial_feeder import (
    build_radial_feeder, LN_S01, LN_S13, LN_S02, LN_S24, LN_TIE,
    BUS_F1B, BUS_F2B,
)


GRID_IEEE14 = "Grids_and_profiles/grids/IEEE 14 bus.raw"


@dataclass
class PassCriteria:
    """通过判据。任一字段未达到即失败。"""
    min_v: float = 0.95
    max_load_pct: float = 110.0
    max_blackout_steps: int = 0


@dataclass
class Scenario:
    name: str
    description: str
    category: str
    grid_factory: Callable
    schedule: list
    duration: float
    pass_criteria: PassCriteria = field(default_factory=PassCriteria)
    key_v_bus: str = ""  # 用于 blackout 检查的母线


def ieee14_factory():
    return vg.open_file(GRID_IEEE14)


def radial_factory():
    return build_radial_feeder()


def radial_heavy_factory():
    return build_radial_feeder(load_p=10.0, load_q=3.5, line_rate=12.0)


# ============================================================ 场景定义
SCENARIOS: list[Scenario] = [
    # ---------- IEEE 14 ----------
    Scenario(
        name="ieee14_N1_line1_2",
        description="N-1: 线路 1-2 跳闸（影响最重负载路径）",
        category="N-1",
        grid_factory=ieee14_factory,
        schedule=make_schedule((5.0, "line_trip", "1_2_1")),
        duration=30.0,
        pass_criteria=PassCriteria(min_v=0.92, max_load_pct=130.0, max_blackout_steps=0),
        key_v_bus="BUS 14",
    ),
    Scenario(
        name="ieee14_N1_g2_trip",
        description="N-1: 发电机 2_1 跳机（BUS 2 上的 G2）",
        category="N-1",
        grid_factory=ieee14_factory,
        schedule=make_schedule((5.0, "gen_trip", "2_1")),
        duration=30.0,
        pass_criteria=PassCriteria(min_v=0.92, max_load_pct=130.0, max_blackout_steps=0),
        key_v_bus="BUS 14",
    ),
    Scenario(
        name="ieee14_load_step",
        description="负荷阶跃: BUS 14 +80MW",
        category="负荷",
        grid_factory=ieee14_factory,
        schedule=make_schedule((5.0, "load_add", "BUS 14", 80.0)),
        duration=30.0,
        pass_criteria=PassCriteria(min_v=0.93, max_load_pct=130.0, max_blackout_steps=0),
        key_v_bus="BUS 14",
    ),
    Scenario(
        name="ieee14_cascade",
        description="级联故障: +50MW → G2 跳 → 线 2-4 跳 → 恢复",
        category="级联",
        grid_factory=ieee14_factory,
        schedule=make_schedule(
            (5.0,  "load_add",  "BUS 14", 50.0),
            (15.0, "gen_trip",  "2_1"),
            (25.0, "line_trip", "2_4_1"),
            (40.0, "line_close", "2_4_1"),
        ),
        duration=50.0,
        pass_criteria=PassCriteria(min_v=0.92, max_load_pct=140.0, max_blackout_steps=0),
        key_v_bus="BUS 14",
    ),

    # ---------- 辐射状 feeder ----------
    Scenario(
        name="radial_s01_trip",
        description="馈线 1 跳闸 -> F1B 失电（R004 应自动恢复）",
        category="馈线故障",
        grid_factory=radial_factory,
        schedule=make_schedule(
            (5.0,  "line_trip", LN_S01),
            (30.0, "line_close", LN_S01),
            (30.0, "line_trip", LN_TIE),
        ),
        duration=40.0,
        pass_criteria=PassCriteria(min_v=0.80, max_load_pct=200.0, max_blackout_steps=5),
        key_v_bus=BUS_F1B,
    ),
    Scenario(
        name="radial_heavy_overload",
        description="重负荷 + 馈线 1 跳闸（R004 + OVL 协同验证）",
        category="馈线故障",
        grid_factory=radial_heavy_factory,
        schedule=make_schedule(
            (5.0, "line_trip", LN_S01),
            (30.0, "line_close", LN_S01),
            (30.0, "line_trip", LN_TIE),
        ),
        duration=40.0,
        pass_criteria=PassCriteria(min_v=0.75, max_load_pct=200.0, max_blackout_steps=5),
        key_v_bus=BUS_F1B,
    ),
    Scenario(
        name="radial_double_fault",
        description="双线故障: S01 + S13 同时跳（仅 F1B 失电，无可恢复路径）",
        category="极限",
        grid_factory=radial_factory,
        schedule=make_schedule(
            (5.0, "line_trip", LN_S01),
            (5.0, "line_trip", LN_S13),
        ),
        duration=30.0,
        pass_criteria=PassCriteria(min_v=0.0, max_load_pct=200.0, max_blackout_steps=999),
        key_v_bus=BUS_F1B,
    ),
]


def list_scenarios(category: str | None = None) -> list[Scenario]:
    """按 category 过滤场景。None 返回全部。"""
    if category is None:
        return list(SCENARIOS)
    return [s for s in SCENARIOS if s.category == category]
