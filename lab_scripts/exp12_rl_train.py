# -*- coding: utf-8 -*-
"""
实验十二：RL 智能体训练（Phase D）
================================================
用 Stable-Baselines3 PPO 在 RadialFeederEnv 上训练，
学习"何时合 TIE"的最优策略。

训练规模：~3000 timesteps（每个 episode 30 步，约 100 episodes）
目标：让 agent 学会在 S01 跳闸后立即合 TIE

对比：
  - Random policy（基线）
  - Rule-based R004（人工规则）
  - RL PPO agent

运行：
  gridcal-env/Scripts/python.exe lab_scripts/exp12_rl_train.py
"""

import warnings
warnings.filterwarnings("ignore")

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rl_env import RadialFeederEnv
from event_sim import Simulator, make_schedule
from rule_engine import build_reconfigure_rule, RuleEngine
from radial_feeder import build_radial_feeder, LN_S01, LN_TIE, BUS_F1B


def evaluate_policy(env, policy_fn, n_episodes: int = 20, seed_base: int = 1000):
    """通用策略评估。policy_fn(obs) -> action

    成功定义：episode 结束时 F1B 电压 >= 0.5（最终恢复）
    """
    returns = []
    successes = 0
    final_v_f1b_list = []
    for ep in range(n_episodes):
        obs, _ = env.reset(seed=seed_base + ep)
        ep_return = 0.0
        last_v_f1b = 0.0
        done = False
        while not done:
            action = policy_fn(obs)
            obs, reward, terminated, truncated, info = env.step(action)
            ep_return += reward
            last_v_f1b = info["v_f1b"]
            done = terminated or truncated
        returns.append(ep_return)
        final_v_f1b_list.append(last_v_f1b)
        if last_v_f1b >= 0.5:
            successes += 1
    return {
        "mean_return": float(np.mean(returns)),
        "std_return": float(np.std(returns)),
        "success_rate": successes / n_episodes,
        "final_v_f1b_mean": float(np.mean(final_v_f1b_list)),
        "returns": returns,
    }


def random_policy(obs):
    return np.random.randint(0, 2)


def rule_based_policy():
    """返回 R004 规则的策略：F1B 失电则合 TIE。"""
    def policy(obs):
        v_f1b = obs[0]
        tie_active = obs[4]
        if v_f1b < 0.5 and not tie_active:
            return 1  # 合 TIE
        return 0  # 不动
    return policy


def train_ppo(env, total_timesteps: int = 3000):
    from stable_baselines3 import PPO
    model = PPO("MlpPolicy", env, verbose=0,
                learning_rate=3e-3,
                n_steps=128,
                batch_size=32)
    model.learn(total_timesteps=total_timesteps)
    return model


def rl_policy(model):
    def policy(obs):
        action, _ = model.predict(obs, deterministic=True)
        return int(action)
    return policy


def main():
    print("=" * 60)
    print("Phase D: RL 智能体训练（PPO 在辐射状 feeder 上）")
    print("=" * 60)

    # ---- 1. 评估 Random baseline
    print("\n[1/3] Random baseline...")
    env = RadialFeederEnv(seed=42)
    rand_stats = evaluate_policy(env, random_policy, n_episodes=30)
    print(f"  mean_return={rand_stats['mean_return']:.2f}  "
          f"success={rand_stats['success_rate']*100:.0f}%  "
          f"F1B final={rand_stats['final_v_f1b_mean']:.3f}")

    # ---- 2. 评估 Rule-based baseline
    print("\n[2/3] Rule-based (R004) baseline...")
    rb_stats = evaluate_policy(env, rule_based_policy(), n_episodes=30)
    print(f"  mean_return={rb_stats['mean_return']:.2f}  "
          f"success={rb_stats['success_rate']*100:.0f}%  "
          f"F1B final={rb_stats['final_v_f1b_mean']:.3f}")

    # ---- 3. 训练 RL
    print("\n[3/3] Training PPO agent (3000 timesteps)...")
    env_train = RadialFeederEnv(seed=42)
    model = train_ppo(env_train, total_timesteps=3000)

    print("\nEvaluating trained PPO agent...")
    env_eval = RadialFeederEnv(seed=42)
    rl_stats = evaluate_policy(env_eval, rl_policy(model), n_episodes=30)
    print(f"  mean_return={rl_stats['mean_return']:.2f}  "
          f"success={rl_stats['success_rate']*100:.0f}%  "
          f"F1B final={rl_stats['final_v_f1b_mean']:.3f}")

    # ---- 汇总
    print("\n" + "=" * 60)
    print("对比结果")
    print("=" * 60)
    print(f"{'策略':<20s} {'mean_return':>12s} {'success':>10s} {'F1B final':>10s}")
    print("-" * 60)
    for name, stats in [("Random", rand_stats), ("Rule-based (R004)", rb_stats),
                         ("RL PPO (3000 steps)", rl_stats)]:
        print(f"{name:<20s} {stats['mean_return']:>12.2f} "
              f"{stats['success_rate']*100:>9.0f}% "
              f"{stats['final_v_f1b_mean']:>9.3f}")

    # ---- 画图：策略对比
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    names = ["Random", "R004", "RL PPO"]
    means = [rand_stats['mean_return'], rb_stats['mean_return'], rl_stats['mean_return']]
    stds = [rand_stats['std_return'], rb_stats['std_return'], rl_stats['std_return']]
    colors = ["lightgray", "lightblue", "salmon"]
    ax.bar(names, means, yerr=stds, color=colors, alpha=0.8)
    ax.set_ylabel("Episode Return")
    ax.set_title("策略对比：平均回报")
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    succ = [rand_stats['success_rate']*100, rb_stats['success_rate']*100, rl_stats['success_rate']*100]
    ax.bar(names, succ, color=colors, alpha=0.8)
    ax.set_ylabel("Success Rate (%)")
    ax.set_title("成功率（无失电）")
    ax.set_ylim(0, 105)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out = "lab_scripts/exp12_rl_train.png"
    plt.savefig(out, dpi=120)
    print(f"\n图已保存到 {out}")

    # 保存模型
    model_path = "lab_scripts/rl_ppo_model"
    model.save(model_path)
    print(f"模型已保存到 {model_path}.zip")


if __name__ == "__main__":
    main()
