# -*- coding: utf-8 -*-
"""
辐射状配电测试 feeder（Phase 2）
================================================
经典 2 馈线 + 1 联络 拓扑：

                SRC (slack, 12.66 kV, vset=1.05)
               /  \
           L01     L02             <- 馈线段 1（带阻抗）
            |      |
           F1A    F2A
            |      |
           L13    L24              <- 馈线段 2（带阻抗）
            |      |
           F1B    F2B
            \    /
             L_TIE                <- 联络段（默认 active=False）

所有"开关"都用 Line 的 active 标志表示：
  - active=True   = 开关闭合
  - active=False  = 开关断开
这样 Line 自身带阻抗（R/X），又可以"投切"，无需额外的 Switch 对象。

负荷：
  F1B: 3.0 MW + j1.0 MVar   （馈线 1 末端）
  F2B: 3.0 MW + j1.0 MVar   （馈线 2 末端）

典型场景：
  A. S01 跳闸 -> F1A/F1B 失电 -> 规则自动闭合 TIE，通过 F2 恢复 F1B 供电
  B. F1A-F1B 段故障 -> 打开 S13 隔离 -> 闭合 TIE 恢复 F1B
"""

import VeraGridEngine as vg
import warnings
warnings.filterwarnings("ignore")


# 元件名称常量（其它代码引用）
BUS_SRC = "SRC"
BUS_F1A = "F1A"
BUS_F1B = "F1B"
BUS_F2A = "F2A"
BUS_F2B = "F2B"

LN_S01 = "S01"      # SRC - F1A（常闭分段）
LN_S13 = "S13"      # F1A - F1B（常闭分段）
LN_S02 = "S02"      # SRC - F2A（常闭分段）
LN_S24 = "S24"      # F2A - F2B（常闭分段）
LN_TIE = "TIE"      # F1B - F2B（常开联络）


def build_radial_feeder(load_p: float = 3.0, load_q: float = 1.0,
                        line_r: float = 0.05, line_x: float = 0.10,
                        tie_r: float = 0.10, tie_x: float = 0.20,
                        sbase: float = 10.0, vnom: float = 12.66,
                        vset: float = 1.05,
                        line_rate: float = 50.0) -> vg.MultiCircuit:
    """构造辐射状配电测试 feeder。所有开关都用 Line + active 表达。

    Parameters
    ----------
    line_rate : float
        线路热稳定限额 (MVA)。默认 50 MVA，对配电馈线合理。
        .gridcal/.raw 文件如果不带 rate，VeraGrid 默认是 1.0（基本没意义）。
    """
    grid = vg.MultiCircuit(name="radial_2feeder_5bus", Sbase=sbase, fbase=50.0)

    # 母线
    b_src = vg.Bus(name=BUS_SRC, Vnom=vnom, is_slack=True)
    b_f1a = vg.Bus(name=BUS_F1A, Vnom=vnom)
    b_f1b = vg.Bus(name=BUS_F1B, Vnom=vnom)
    b_f2a = vg.Bus(name=BUS_F2A, Vnom=vnom)
    b_f2b = vg.Bus(name=BUS_F2B, Vnom=vnom)
    for b in (b_src, b_f1a, b_f1b, b_f2a, b_f2b):
        grid.add_bus(b)

    # 电源
    grid.add_generator(b_src, vg.Generator(name="G_SRC", P=0.0, vset=vset))

    # 负荷
    grid.add_load(b_f1b, vg.Load(name="L1", P=load_p, Q=load_q))
    grid.add_load(b_f2b, vg.Load(name="L2", P=load_p, Q=load_q))

    # 线路（每条馈线两段）
    ln_s01 = vg.Line(name=LN_S01, bus_from=b_src, bus_to=b_f1a,
                     r=line_r, x=line_x, b=0.0)
    ln_s13 = vg.Line(name=LN_S13, bus_from=b_f1a, bus_to=b_f1b,
                     r=line_r, x=line_x, b=0.0)
    ln_s02 = vg.Line(name=LN_S02, bus_from=b_src, bus_to=b_f2a,
                     r=line_r, x=line_x, b=0.0)
    ln_s24 = vg.Line(name=LN_S24, bus_from=b_f2a, bus_to=b_f2b,
                     r=line_r, x=line_x, b=0.0)
    ln_tie = vg.Line(name=LN_TIE, bus_from=b_f1b, bus_to=b_f2b,
                     r=tie_r, x=tie_x, b=0.0)

    for ln in (ln_s01, ln_s13, ln_s02, ln_s24, ln_tie):
        ln.rate = line_rate  # 显式设置热稳定限额
        grid.add_line(ln)

    # 联络默认断开（其它保持闭合）
    ln_tie.active = False

    return grid


def describe(grid) -> str:
    """返回馈线结构的人类可读描述。"""
    lines = []
    lines.append(f"电网: {grid.name}")
    lines.append(f"  母线 ({len(grid.buses)}): "
                 + ", ".join(b.name for b in grid.buses))
    lines.append(f"  发电机: "
                 + ", ".join(f"{g.name}@{g.bus.name}(Pset={g.P:.1f}MW, vset={g.Vset:.3f})"
                             for g in grid.get_generators()))
    lines.append(f"  负荷: "
                 + ", ".join(f"{ld.name}@{ld.bus.name}({ld.P:.1f}+j{ld.Q:.1f})"
                             for ld in grid.get_loads()))
    lines.append(f"  线路/开关 ({len(grid.lines)}):")
    for ln in grid.lines:
        state = "闭合" if ln.active else "断开"
        lines.append(f"    {ln.name}: {ln.bus_from.name}->{ln.bus_to.name} "
                     f"(R={ln.R:.3f}, X={ln.X:.3f}) [{state}]")
    return "\n".join(lines)


if __name__ == "__main__":
    import numpy as np
    grid = build_radial_feeder()
    print(describe(grid))

    pf = vg.power_flow(grid)
    print(f"\n基线潮流: converged={pf.converged}, loss={pf.Sbus.real.sum():.3f}MW")
    print("  母线电压 (pu): "
          + ", ".join(f"{b.name}={abs(v):.4f}" for b, v in zip(grid.buses, pf.voltage)))

    # 模拟 S01 跳闸 -> F1A/F1B 失电
    for ln in grid.lines:
        if ln.name == LN_S01:
            ln.active = False
    pf2 = vg.power_flow(grid)
    print(f"\nS01 断开后: converged={pf2.converged}, loss={pf2.Sbus.real.sum():.3f}MW")
    print("  母线电压 (pu): "
          + ", ".join(f"{b.name}={abs(v):.4f}" for b, v in zip(grid.buses, pf2.voltage)))

    # 闭合 TIE 恢复 F1B
    for ln in grid.lines:
        if ln.name == LN_TIE:
            ln.active = True
    pf3 = vg.power_flow(grid)
    print(f"\nS01 断开 + TIE 闭合后: converged={pf3.converged}, loss={pf3.Sbus.real.sum():.3f}MW")
    print("  母线电压 (pu): "
          + ", ".join(f"{b.name}={abs(v):.4f}" for b, v in zip(grid.buses, pf3.voltage)))
