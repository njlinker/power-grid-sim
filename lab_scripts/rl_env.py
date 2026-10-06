# -*- coding: utf-8 -*-
"""
Gymnasium 环境封装（Phase D）
================================================
把 Simulator 包成 RL 训练用的环境。

任务：
  在 5-bus 辐射状 feeder 上，agent 必须学会：
    - 观察母线电压（任何 F1B V < 0.5 视为失电）
    - 决策：合 TIE / 不合 TIE
    - 当 S01 跳闸导致 F1B 失电时，要尽快合 TIE

状态（6 维）:
  - F1B 电压（pu）
  - F2B 电压（pu）
  - F1A 电压（pu）
  - F2A 电压（pu）
  - TIE 开关状态（0/1）
  - 时间归一化（t/duration）

动作（2 维 discrete）:
  - 0: 不动
  - 1: 合 TIE

奖励：
  - 每步：+1（系统正常）/ -5（F1B 失电）
  - 动作：合 TIE -0.1（鼓励小动作）
  - 终止：恢复 +10 / 失败 -10
"""

from __future__ import annotations

import numpy as np
from typing import Optional

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    import gym
    from gym import spaces

import VeraGridEngine as vg

from event_sim import Simulator
from radial_feeder import build_radial_feeder, LN_S01, LN_TIE, BUS_F1B


class RadialFeederEnv(gym.Env):
    """5-bus 辐射状 feeder 的 RL 环境。"""

    metadata = {"render_modes": []}

    def __init__(self, episode_steps: int = 30, fault_time_range=(5, 15),
                 seed: Optional[int] = None):
        super().__init__()
        self.episode_steps = episode_steps
        self.fault_time_range = fault_time_range
        self.rng = np.random.default_rng(seed)

        # 状态：F1B V, F2B V, F1A V, F2A V, TIE 状态, 时间归一化
        self.observation_space = spaces.Box(
            low=np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            high=np.array([1.2, 1.2, 1.2, 1.2, 1.0, 1.0], dtype=np.float32),
        )
        # 动作：0=不动, 1=合 TIE
        self.action_space = spaces.Discrete(2)

        self.grid = None
        self.sim = None
        self.t = 0
        self.tie = None

    def reset(self, *, seed: Optional[int] = None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)

        self.grid = build_radial_feeder()
        # 找到 TIE 引用
        self.tie = next(ln for ln in self.grid.lines if ln.name == LN_TIE)
        self.tie.active = False  # 起始断开

        # 随机化故障时间
        fault_t = int(self.rng.integers(self.fault_time_range[0],
                                        self.fault_time_range[1] + 1))
        self.sim = Simulator(self.grid, dt=1.0, verbose=False)
        # 预注入 S01 trip 在 fault_t
        from event_sim import Event
        self._fault_event = Event(t=float(fault_t), kind="line_trip", target=LN_S01)

        # 跑基线 (t=0)
        self.t = 0.0
        from event_sim import snapshot
        import VeraGridEngine as _vg
        pf = _vg.power_flow(self.grid, options=_vg.PowerFlowOptions(solver_type=_vg.SolverType.NR))
        self._last_snapshot = snapshot(self.grid, pf, t=0.0)
        return self._get_obs(), {}

    def _get_obs(self) -> np.ndarray:
        snap = self._last_snapshot
        return np.array([
            snap.get(f"v_{BUS_F1B}", 0.0) or 0.0,
            snap.get(f"v_F2B", 0.0) or 0.0,
            snap.get(f"v_F1A", 0.0) or 0.0,
            snap.get(f"v_F2A", 0.0) or 0.0,
            float(self.tie.active),
            self.t / self.episode_steps,
        ], dtype=np.float32)

    def step(self, action: int):
        # 应用动作
        reward = 0.0
        if action == 1 and not self.tie.active:
            self.tie.active = True
            reward -= 0.1  # 小惩罚，鼓励最小动作
        elif action == 1 and self.tie.active:
            reward -= 0.05  # 重复合，浪费

        # 时间推进 1 步
        self.t += 1.0
        # 在 fault_t 触发 line_trip
        if hasattr(self, "_fault_event") and abs(self.t - self._fault_event.t) < 0.5:
            from event_sim import inject
            # 构造新 Event 避免修改 frozen dataclass
            new_ev = type(self._fault_event)(
                t=self.t,
                kind=self._fault_event.kind,
                target=self._fault_event.target,
                magnitude=self._fault_event.magnitude,
            )
            inject(self.grid, new_ev)

        # 重新潮流
        pf = vg.power_flow(self.grid,
                           options=vg.PowerFlowOptions(solver_type=vg.SolverType.NR))
        from event_sim import snapshot
        self._last_snapshot = snapshot(self.grid, pf, t=self.t)

        # 计算奖励
        v_f1b = self._last_snapshot.get(f"v_{BUS_F1B}", 0.0) or 0.0
        blackout = (v_f1b < 0.5)
        if blackout:
            reward -= 5.0
        else:
            reward += 1.0

        # 终止条件
        terminated = False
        truncated = (self.t >= self.episode_steps)
        if truncated:
            if not blackout:
                reward += 5.0  # 恢复奖励
            else:
                reward -= 5.0  # 失败惩罚

        info = {
            "v_f1b": v_f1b,
            "tie_active": float(self.tie.active),
            "blackout": blackout,
        }
        return self._get_obs(), reward, terminated, truncated, info

    def render(self):
        pass
