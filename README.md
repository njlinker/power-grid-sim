# PowerGridSim

> ⚡ Event-driven power grid simulation with auto-switching decision system.
> 电网事件驱动仿真与自动投切决策系统。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![JOSS](https://img.shields.io/badge/JOSS-submission-blue)](https://joss.theoj.org/)

---

## What is PowerGridSim?

PowerGridSim is an **event-driven power grid simulation platform** built on [VeraGrid](https://github.com/SanPen-Alcon/VeraGrid). It enables researchers and engineers to:

1. **Simulate grid disturbances** — load changes, generator trips, line faults
2. **Auto-generate protection rules** — discover optimal IF-THEN policies via simulation
3. **Visualize state evolution** — interactive Plotly and Dash dashboards
4. **Evaluate probabilistic behavior** — Monte Carlo under load uncertainty

The framework integrates topology analysis, rule engines, reinforcement learning, and statistical evaluation in a single Python package.

## Statement of Need

Existing power system simulators (PSS/E, DIgSILENT, GridCal) excel at steady-state and dynamic analysis but typically do **not** provide:

- A unified Python API for **event injection** (load add/drop, gen trip, line trip)
- Built-in **rule engines** for protection/reconfiguration with cooldown
- **Topology-aware auto-reconfiguration** with fault isolation
- **Probabilistic power flow** integrated with the same simulator
- **Interactive web dashboards** for live visualization

PowerGridSim fills this gap with an end-to-end Python workflow designed for **distribution automation research**.

## Installation

### From source (current)

```bash
git clone https://github.com/<your-name>/power-grid-sim.git
cd power-grid-sim

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest
```

### Dependencies

Core:
- [VeraGrid](https://pypi.org/project/VeraGrid/) >= 6.0 — power flow solver
- numpy, pandas — data manipulation
- pyyaml — rule configuration files

Visualization (optional):
- matplotlib — static plots
- plotly — interactive HTML dashboards

Advanced features (optional):
- stable-baselines3, gymnasium — reinforcement learning (Phase D)
- dash — real-time live dashboard (Phase F)

## Quick Start

```python
from event_sim import Simulator, make_schedule
from rules_loader import load_engine_from_yaml
import VeraGridEngine as vg

# Load a grid
grid = vg.open_file("Grids_and_profiles/grids/IEEE 14 bus.raw")

# Define an event schedule
schedule = make_schedule(
    (10.0, "load_add", "BUS 14", 50.0),   # +50MW at bus 14 at t=10s
    (40.0, "gen_trip", "2_1"),            # Generator 2 trips at t=40s
)

# Load rules from YAML
engine = load_engine_from_yaml("lab_scripts/config/rules.yaml")

# Run simulation
sim = Simulator(grid, dt=1.0)
df = sim.run(duration=90.0, schedule=schedule, rules=engine)

# Inspect results
print(df[['t', 'v_BUS 14', 'line_1_2_1', 'loss_mw']].tail())
```

## Repository Structure

```
power-grid-sim/
├── docs/
│   └── DESIGN.md              # Detailed design doc (370+ lines)
├── lab_scripts/
│   ├── event_sim.py           # Event injection + simulator
│   ├── rule_engine.py         # Rule + RuleEngine + 4 default rules
│   ├── radial_feeder.py       # 5-bus radial feeder test system
│   ├── load_profiles.py       # ZIP model + flicker + switching
│   ├── rule_generator.py      # Candidate enumeration + scoring
│   ├── topology_analyzer.py   # Topology analysis (tie_map, etc.)
│   ├── rules_loader.py        # YAML rule configuration
│   ├── scenarios.py           # Test scenario library
│   ├── dashboard.py           # Plotly dashboard builder
│   ├── rl_env.py              # Gymnasium RL environment
│   ├── config/
│   │   └── rules.yaml         # Default rule configuration
│   └── exp01...exp14*.py      # 14 demo scripts
├── tests/                     # pytest test suite (64 tests)
├── Grids_and_profiles/        # IEEE / Kundur test systems
├── paper.md                   # JOSS submission paper
├── docs/DESIGN.md             # Full design documentation
├── LICENSE                    # MIT License
├── CITATION.cff               # Citation metadata
├── pytest.ini                 # pytest configuration
└── README.md                  # This file
```

## Core Capabilities

| Phase | Feature | Key Metric |
|---|---|---|
| **1. Event-Driven Sim** | 6 event types, snapshot/state | 91/91 steps converged |
| **2. Topology Control** | 5-bus radial feeder, switch modeling | F1B blackout 25→1 step |
| **3. Rule Engine** | 4 default rules (UVLS/OVGR/OVL/RECONF) | min_v +0.010 pu, load −15% |
| **B. Real Loads** | ZIP + flicker + switching prob | 11 profiles, 201/201 converged |
| **4. Rule Generation** | Enumerate + simulate + score | 30+ candidates ranked |
| **5. Visualization** | Plotly HTML + Dash live | 264 KB single-file dashboard |
| **A. YAML Config** | Rules without code changes | 4 rules from rules.yaml |
| **C. R004 v2** | Auto tie_map + fault isolation | S13 isolation verified |
| **D. RL Agent** | PPO in Gymnasium env | Framework + trained model |
| **E. Probabilistic PF** | Monte Carlo with N(0,σ) load noise | 200 runs, 79.5% overload prob |
| **F. Real-Time Dash** | Dash + interval callback | 1-second auto-refresh |

## Running the Demos

```bash
cd lab_scripts

# Phase 1: event-driven simulation
python exp03_event_driven_sim.py

# Phase 2: reconfiguration
python exp05_reconfigure.py

# Phase 3: rule engine comparison
python exp04_rule_engine.py

# Phase 4: rule generation
python exp07_rule_generation.py

# Phase 5: Plotly dashboard (single HTML)
python exp08_dashboard.py
# Open lab_scripts/exp08_dashboard.html in browser

# Phase 6: live Dash server
python exp14_dash_live.py
# Open http://127.0.0.1:8050

# Benchmarks
python exp10_benchmark.py    # 7 scenarios with pass/fail

# Probability flow
python exp13_ppf.py          # Monte Carlo with 200 runs
```

## Testing

```bash
pytest                    # Run all 64 tests
pytest -v                 # Verbose
pytest tests/test_event_sim.py   # Single module
pytest --tb=long           # Full traceback on failure
```

Test coverage includes:
- Event injection and Simulator loop
- Rule engine + cooldown logic
- Topology analysis (tie_map, fault isolation)
- Load profiles (ZIP, flicker, switching)
- YAML rule loading
- Rule generation and scoring

## Documentation

- **[docs/DESIGN.md](docs/DESIGN.md)** — 370+ line design document with API quirks, decision rationale, validation results
- **Lab scripts** — each script is heavily commented; see `exp03`, `exp05`, `exp07` as entry points
- **Docstrings** — every public function has type hints and docstrings

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Add tests for new functionality
4. Ensure `pytest` passes
5. Submit a pull request

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

## Citation

If you use PowerGridSim in research, please cite:

```bibtex
@software{powergridsim2026,
  author = {liu, ka},
  title = {PowerGridSim: Event-Driven Grid Simulation with Auto-Switching Decision System},
  year = {2026},
  journal = {Journal of Open Source Software},
  url = {https://github.com/njlinker/power-grid-sim},
  doi = {10.5281/zenodo.23232208}
}
```

See [CITATION.cff](CITATION.cff) for machine-readable citation metadata.

## Acknowledgments

- Built on top of [VeraGrid](https://github.com/SanPen-Alcon/VeraGrid) by Santiago Peñate Vera et al.
- Visualization powered by [Plotly](https://plotly.com/) and [Dash](https://dash.plotly.com/)
- Reinforcement learning via [Stable-Baselines3](https://stable-baselines3.readthedocs.io/)
- Test systems from IEEE Power & Energy Society and Kundur

## Related Projects

- [VeraGrid](https://github.com/SanPen-Alcon/VeraGrid) — base power system simulator
- [GridCal](https://github.com/SanPen-Alcon/GridCal) — predecessor project
- [PyPSA](https://github.com/PyPSA/PyPSA) — Python for Power Systems Analysis
- [OpenDSS](https://sourceforge.net/projects/electricdss/) — EPRI distribution system simulator

## Contact

For questions or feedback, please open an issue on GitHub.
