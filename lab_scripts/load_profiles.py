# -*- coding: utf-8 -*-
"""
真实负荷扰动层（Phase B）
================================================
为仿真器提供真实负荷特性：
  1. ZIP 模型     — P(V) = α_z·V² + α_i·V + α_p，三类负荷的加权组合
                    恒阻抗（电阻加热/照明）、恒电流（整流）、恒功率（变频器/开关电源）
  2. 闪烁/闪变    — P(t) = P_base·(1 + A·sin(2π·f·t))，模拟变频器/电弧炉等非稳态
  3. 随机启停    — 每步按概率切换 active 状态，模拟工厂负荷不定时开关

用法：
    profiler = LoadProfiler()
    profiler.add(LoadProfile(
        bus_name="BUS 14",
        base_p=14.9, base_q=5.0,
        zip_z=0.2, zip_i=0.3, zip_p=0.5,         # 偏电力电子
        flicker_amp=0.05, flicker_freq=8.0,       # 8Hz 闪变 5%
        switch_on_prob=0.0, switch_off_prob=1e-4,  # 极低停机概率
    ))
    sim = Simulator(grid, profiler=profiler)

ZIP 模型细节：
    设 V0=1.0 pu 为额定电压，实际电压 V 下：
        P(V) = P_base · [α_z·(V/V0)² + α_i·(V/V0) + α_p]
    三类典型设备：
        - 恒阻抗（Z）：白炽灯、电阻加热、电弧炉（近似）
        - 恒电流（I）：整流器（中等）
        - 恒功率（P）：变频器、开关电源、异步电机（启动后）
        注意：恒功率负荷有"负增量阻抗"特性，恶化电压稳定性
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

import VeraGridEngine as vg
import warnings
warnings.filterwarnings("ignore")


@dataclass
class LoadProfile:
    """某母线上的负荷时序模型。

    Attributes
    ----------
    bus_name : str
        目标母线名（按 grid.buses 上的 .name）
    base_p : float
        基线有功 (MW)
    base_q : float
        基线无功 (MVar)
    zip_z, zip_i, zip_p : float
        三类负荷占比（z+i+p=1 推荐，但不强校验）
    flicker_amp : float
        闪烁幅度 (pu of P_base)，0=无闪变
    flicker_freq : float
        闪烁频率 (Hz)，0=无闪变
    switch_on_prob : float
        每秒启动概率（0=始终关闭，1=必启动）
    switch_off_prob : float
        每秒停机概率
    state : int
        初始状态：1=运行, 0=停机
    label : str
        可选的人类可读标签
    """
    bus_name: str
    base_p: float
    base_q: float = 0.0
    zip_z: float = 0.3
    zip_i: float = 0.3
    zip_p: float = 0.4
    flicker_amp: float = 0.0
    flicker_freq: float = 0.0
    switch_on_prob: float = 0.0
    switch_off_prob: float = 0.0
    state: int = 1
    label: str = ""

    def __post_init__(self):
        if self.zip_z < 0 or self.zip_i < 0 or self.zip_p < 0:
            raise ValueError(f"ZIP 系数必须非负: z={self.zip_z}, i={self.zip_i}, p={self.zip_p}")


class LoadProfiler:
    """管理一组 LoadProfile，每步推进其状态并把 P/Q 写回 grid 中的 Load 对象。"""

    def __init__(self, profiles: Optional[list[LoadProfile]] = None,
                 vnom: float = 1.0, seed: Optional[int] = None):
        self.profiles: list[LoadProfile] = list(profiles or [])
        self.vnom = float(vnom)
        self._last_v: dict[str, float] = {}  # 上一步母线电压（ZIP 用）
        self._rng = np.random.default_rng(seed)
        self._history: list[dict] = []  # 记录每步每个 profile 的实际 P/Q

    def add(self, profile: LoadProfile):
        self.profiles.append(profile)

    def reset(self, seed: Optional[int] = None):
        """重置所有 profile 状态和历史。"""
        for p in self.profiles:
            p.state = 1
        self._last_v.clear()
        self._history.clear()
        if seed is not None:
            self._rng = np.random.default_rng(seed)

    def tick(self, grid, t: float, dt: float) -> dict:
        """推进一个仿真步：更新启停、闪烁、ZIP 折算，写入 grid。

        Returns
        -------
        dict : {profile_label_or_name: {"P": ..., "Q": ..., "state": ...}}
        """
        snapshot = {}

        for prof in self.profiles:
            # ---- 1. 启停状态转移
            if prof.state == 1 and prof.switch_off_prob > 0:
                # 每步转移概率 = rate * dt（rate 单位 1/秒）
                p = min(prof.switch_off_prob * dt, 1.0)
                if self._rng.random() < p:
                    prof.state = 0
            elif prof.state == 0 and prof.switch_on_prob > 0:
                p = min(prof.switch_on_prob * dt, 1.0)
                if self._rng.random() < p:
                    prof.state = 1

            # ---- 2. 计算 P/Q
            # ZIP 折算（用上一步电压）
            v = self._last_v.get(prof.bus_name, self.vnom)
            v_safe = max(v, 0.4)  # 防止电压塌缩导致 ZIP 折算出负数
            ratio = v_safe / self.vnom
            zip_factor = (prof.zip_z * ratio**2
                          + prof.zip_i * ratio
                          + prof.zip_p)

            # 闪烁分量（叠加在 ZIP 后的 P 上）
            flicker = 0.0
            if prof.flicker_amp > 0 and prof.flicker_freq > 0:
                flicker = prof.flicker_amp * np.sin(2 * np.pi * prof.flicker_freq * t)

            p_eff = max(prof.base_p * (1.0 + flicker) * zip_factor * prof.state, 0.0)
            q_eff = max(prof.base_q * zip_factor * prof.state, 0.0)

            # ---- 3. 写回 grid
            loads = [ld for ld in grid.get_loads() if ld.bus.name == prof.bus_name]
            if not loads:
                continue
            # 优先匹配已有动态负荷；否则改第一个同名母线负荷
            target = loads[0]
            # 多个负荷时把功率合并写到第一个
            total_base = sum(ld.P for ld in loads) if any(ld.P > 0 for ld in loads) else p_eff
            target.P = p_eff
            target.Q = q_eff
            target.active = prof.state > 0

            key = prof.label or f"{prof.bus_name}@{prof.base_p:.1f}MW"
            snapshot[key] = {
                "P": p_eff, "Q": q_eff, "state": prof.state,
                "v_used": v, "flicker": flicker, "zip_f": zip_factor,
            }

        self._history.append({"t": t, **snapshot})
        return snapshot

    def update_v(self, v_dict: dict[str, float]):
        """PF 完成后调用，把各母线电压存起来供下一步 ZIP 计算。"""
        self._last_v.update(v_dict)

    def history_dataframe(self):
        """把历史记录展开成 DataFrame，便于分析。"""
        import pandas as pd
        rows = []
        for snap in self._history:
            t = snap["t"]
            for key, val in snap.items():
                if key == "t":
                    continue
                rows.append({
                    "t": t, "load": key,
                    "P": val["P"], "Q": val["Q"],
                    "state": val["state"],
                    "flicker": val["flicker"],
                    "zip_f": val["zip_f"],
                })
        return pd.DataFrame(rows)


# ============================================================ 预设 profile 模板
def industrial_factory(bus_name: str, base_p: float, base_q: float = 0.0) -> LoadProfile:
    """工厂负荷模板：偏恒功率（异步电机）+ 间歇停机。"""
    return LoadProfile(
        bus_name=bus_name, base_p=base_p, base_q=base_q,
        zip_z=0.2, zip_i=0.3, zip_p=0.5,
        switch_off_prob=2e-4, switch_on_prob=8e-4,  # 平均 ~1.4h 停一次
        label=f"工厂@{bus_name}",
    )


def vfd_load(bus_name: str, base_p: float, base_q: float = 0.0) -> LoadProfile:
    """变频器/整流器负荷模板：纯恒功率 + 8Hz 闪变。"""
    return LoadProfile(
        bus_name=bus_name, base_p=base_p, base_q=base_q,
        zip_z=0.0, zip_i=0.0, zip_p=1.0,  # 纯恒功率
        flicker_amp=0.05, flicker_freq=8.0,
        label=f"变频器@{bus_name}",
    )


def residential(bus_name: str, base_p: float, base_q: float = 0.0) -> LoadProfile:
    """居民负荷模板：偏恒阻抗（白炽灯/家电）+ 随机启停。"""
    return LoadProfile(
        bus_name=bus_name, base_p=base_p, base_q=base_q,
        zip_z=0.6, zip_i=0.2, zip_p=0.2,
        switch_off_prob=1e-3, switch_on_prob=2e-3,
        label=f"居民@{bus_name}",
    )
