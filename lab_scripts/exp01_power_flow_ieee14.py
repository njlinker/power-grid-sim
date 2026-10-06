# -*- coding: utf-8 -*-
"""
实验一：潮流计算（Newton-Raphson 与 P-Q 解耦对照）
====================================================
知识点：节点导纳矩阵、功率方程、NR 迭代、P-Q 解耦近似、网损

算例：IEEE 14 节点系统（PSS/E .raw 格式直接导入）
运行：gridcal-env/Scripts/python.exe lab_scripts/exp01_power_flow_ieee14.py
"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import VeraGridEngine as vg

GRID_FILE = "Grids_and_profiles/grids/IEEE 14 bus.raw"

# ---------------------------------------------------------------- 1. 建模与求解
grid = vg.open_file(GRID_FILE)
print(f"算例: {GRID_FILE}")
print(f"节点 {len(grid.buses)} | 线路 {len(grid.lines)} | 变压器 {len(grid.transformers2w)} "
      f"| 发电机 {len(grid.get_generators())} | 负荷 {len(grid.get_loads())}")
print(f"基准容量 Sbase = {grid.Sbase} MVA, 基准频率 fbase = {grid.fBase} Hz")

# Newton-Raphson 全量迭代法（教材标准算法）
res_nr = vg.power_flow(grid, options=vg.PowerFlowOptions(solver_type=vg.SolverType.NR))
print(f"\n[NR] 收敛: {res_nr.converged} | 迭代: {res_nr.iterations} 次 | 失配量: {res_nr.error:.3e}")

# P-Q 解耦（快速解耦，教材重点近似算法）
res_fd = vg.power_flow(grid, options=vg.PowerFlowOptions(solver_type=vg.SolverType.FASTDECOUPLED))
print(f"[FD] 收敛: {res_fd.converged} | 迭代: {res_fd.iterations} 次 | 失配量: {res_fd.error:.3e}")

# ------------------------------------------------- 2. 两种算法的电压结果最大偏差
dv = np.max(np.abs(np.abs(res_nr.voltage) - np.abs(res_fd.voltage)))
da = np.max(np.abs(np.degrees(np.angle(res_nr.voltage) - np.angle(res_fd.voltage))))
print(f"\nNR 与 P-Q 解耦结果偏差:  Δ|V|max = {dv:.2e} pu,  Δδmax = {da:.2e} deg")

# ---------------------------------------------------------- 3. 节点电压结果表
print("\n=== 节点电压（NR） ===")
print(f"{'节点':<8}{'类型':<6}{'|V| (pu)':>10}{'δ (deg)':>10}")
for name, t, v in zip(res_nr.bus_names, res_nr.bus_types, res_nr.voltage):
    tname = {1: "PQ", 2: "PV", 3: "Slack"}.get(int(t), str(int(t)))
    print(f"{name:<8}{tname:<6}{float(abs(v)):>10.4f}{float(np.degrees(np.angle(v))):>10.3f}")

# ---------------------------------------------------------- 4. 支路潮流
# 注：PSS/E .raw 文件未填写支路额定值（RATEA=0），负载率无意义，本实验只看潮流数值。
#     额定值与越限分析在实验三中处理（IEEE 30 .raw 自带额定值）。
print("\n=== 支路潮流（送端，NR） ===")
print(f"{'支路':<16}{'P (MW)':>10}{'Q (MVAr)':>10}{'|S| (MVA)':>12}")
for name, sf in zip(res_nr.branch_names, res_nr.Sf):
    print(f"{name:<16}{float(sf.real):>10.2f}{float(sf.imag):>10.2f}{float(abs(sf)):>12.2f}")

# ---------------------------------------------------------- 5. 全网损耗汇总
print(f"\n全网有功损耗: {res_nr.losses.real.sum():.2f} MW | 无功损耗: {res_nr.losses.imag.sum():.2f} MVAr")

print("\n思考题：")
print(" 1) 为什么 P-Q 解耦迭代次数多但单次迭代更快？结果偏差量级说明什么？")
print(" 2) 找出负载率最高的支路，若其退出运行会发生什么？（引出实验三）")
print(" 3) 用 get_bus_df() 导出结果并与教材附录 IEEE14 标准答案对照。")
