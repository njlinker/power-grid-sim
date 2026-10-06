# -*- coding: utf-8 -*-
"""
实验二：短路电流计算（三相短路 + 单相接地对照）
====================================================
知识点：对称分量法、正/负/零序网络、金属性短路、短路容量

算例：IEEE 14 节点（PSS/E .raw）
运行：gridcal-env/Scripts/python.exe lab_scripts/exp02_short_circuit_ieee14.py

API 说明（VeraGrid 6.0.22 实测）：
  - vg.short_circuit(grid, fault_index=母线下标, fault_type=..., pf_results=潮流结果)
  - fault_type 取自 vg.FaultType：LLLG=三相短路(经地)、LG=单相接地、LL=两相、LLG=两相接地
  - 结果为序分量/相分量数组：voltage1=正序电压, If1=支路正序故障电流, Sbus1=正序功率
"""
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import VeraGridEngine as vg

GRID_FILE = "Grids_and_profiles/grids/IEEE 14 bus.raw"
FAULT_BUS = 2          # 母线下标（0 起）：BUS 3
SQRT3 = np.sqrt(3.0)


def run_fault(fault_type, label):
    """对同一故障点施加指定类型金属性短路，返回 (grid, pf, sc)。"""
    grid = vg.open_file(GRID_FILE)          # 每次重新读入，避免短路事件叠加
    pf = vg.power_flow(grid, options=vg.PowerFlowOptions(solver_type=vg.SolverType.NR))
    sc = vg.short_circuit(grid, fault_index=FAULT_BUS, fault_type=fault_type, pf_results=pf)
    print(f"\n===== {label} @ {grid.buses[FAULT_BUS].name} (Vnom={grid.buses[FAULT_BUS].Vnom} kV) =====")
    return grid, pf, sc


def report(grid, pf, sc, seq_col=0):
    """打印故障期间正序电压分布、相连支路故障电流、故障点总短路电流。"""
    v_pre = abs(pf.voltage[FAULT_BUS])
    v1 = sc.voltage1[:, seq_col]
    print(f"故障前电压: {v_pre:.4f} pu   故障期间正序电压:")
    for name, v in zip(sc.bus_names, v1):
        mark = "  <-- 故障点" if name == grid.buses[FAULT_BUS].name else ""
        print(f"  {name:<10}{float(abs(v)):>8.4f} pu{mark}")

    # 与故障点相连的支路：正序故障电流（从端 If1 / 到端 It1）
    fbus = grid.buses[FAULT_BUS]
    i_total = 0.0
    print("相连支路故障电流（正序）:")
    branches = list(grid.lines) + list(grid.transformers2w)
    for k, br in enumerate(branches):
        if br.bus_from is fbus or br.bus_to is fbus:
            i_f = float(abs(sc.If1[k, seq_col]))
            i_t = float(abs(sc.It1[k, seq_col]))
            i_total += max(i_f, i_t)
            print(f"  {br.name:<16} If={i_f:.4f} pu  It={i_t:.4f} pu")

    sbase = grid.Sbase                       # MVA
    vnom = fbus.Vnom                         # kV
    i_base_ka = sbase / (SQRT3 * vnom)       # 基准电流 kA
    scc_mva = i_total * sbase                # 短路容量（近似：金属性故障）
    print(f"故障点总短路电流: {i_total:.4f} pu = {i_total * i_base_ka:.3f} kA "
          f"(基准电流 {i_base_ka:.3f} kA)")
    print(f"短路容量 SCC ≈ {scc_mva:.1f} MVA")
    return i_total


# ------------------------------------------------------------ 1. 三相短路（LLLG）
g3, pf3, sc3 = run_fault(vg.FaultType.LLLG, "三相短路 LLLG")
i_3ph = report(g3, pf3, sc3)

# ------------------------------------------------------------ 2. 单相接地（LG）
g1, pf1, sc1 = run_fault(vg.FaultType.LG, "单相接地 LG")
i_lg = report(g1, pf1, sc1)

# ------------------------------------------------------------ 3. 对照与思考
print("\n=== 对照 ===")
print(f"三相短路电流 {i_3ph:.4f} pu  vs  单相接地电流 {i_lg:.4f} pu  "
      f"比值 = {i_3ph / i_lg:.3f}")
print("\n思考题：")
print(" 1) 故障点正序电压为何≈0？非故障相电压如何变化？（查看 sc.voltageA/B/C）")
print(" 2) 三相与单相接地电流比值取决于什么网络参数？（正/负/零序阻抗的关系）")
print(" 3) 换一台母线（改 FAULT_BUS），比较发电机近端/远端的短路容量差异。")
