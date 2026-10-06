"""
VeraGrid 安装验证：构建一个 5 节点小电网并跑潮流计算
"""
from VeraGridEngine.api import (
    MultiCircuit, Bus, Generator, Load, Line,
    PowerFlowDriver, PowerFlowOptions, SolverType,
)

grid = MultiCircuit(name="demo_5bus", Sbase=100.0, fbase=50.0)

b1 = Bus(name="B1", Vnom=20.0, is_slack=True)
b2 = Bus(name="B2", Vnom=20.0)
b3 = Bus(name="B3", Vnom=20.0)
b4 = Bus(name="B4", Vnom=20.0)
b5 = Bus(name="B5", Vnom=20.0)
for b in (b1, b2, b3, b4, b5):
    grid.add_bus(b)

grid.add_generator(b1, Generator(name="G1", P=0.0, vset=1.02))
grid.add_load(b3, Load(name="L3", P=20.0, Q=8.0))
grid.add_load(b4, Load(name="L4", P=30.0, Q=12.0))
grid.add_load(b5, Load(name="L5", P=25.0, Q=10.0))

grid.add_line(Line(bus_from=b1, bus_to=b2, name="L1-2", r=0.01, x=0.05, b=0.02))
grid.add_line(Line(bus_from=b2, bus_to=b3, name="L2-3", r=0.02, x=0.06, b=0.02))
grid.add_line(Line(bus_from=b2, bus_to=b4, name="L2-4", r=0.02, x=0.07, b=0.02))
grid.add_line(Line(bus_from=b3, bus_to=b5, name="L3-5", r=0.03, x=0.08, b=0.02))
grid.add_line(Line(bus_from=b4, bus_to=b5, name="L4-5", r=0.02, x=0.06, b=0.02))

print(f"Buses: {len(grid.buses)}  Lines: {len(grid.lines)}  "
      f"Generators: {len(grid.get_generators())}  Loads: {len(grid.get_loads())}")

opts = PowerFlowOptions(solver_type=SolverType.NR, verbose=0)
drv = PowerFlowDriver(grid=grid, options=opts)
drv.run()
res = drv.results

print("\n=== Power Flow Results ===")
print(f"Converged: {res.converged}  Iterations: {res.iterations}  Error: {res.error:.2e}")
print("\nBus voltages (|V| pu, angle deg):")
import numpy as np
for bus, v in zip(grid.buses, res.voltage):
    print(f"  {bus.name}: |V|={abs(v):.4f}  ang={np.degrees(np.angle(v)):+7.3f}")

print("\nLine flows (MW + jMVAr) and loading (%):")
for ln, sf, ld in zip(grid.lines, res.Sf, res.loading):
    print(f"  {ln.name}: Sf={sf.real:+7.2f} + j{sf.imag:+6.2f}   load={ld.real*100:5.1f}%")
