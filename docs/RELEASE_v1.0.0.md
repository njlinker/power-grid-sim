# PowerGridSim v1.0.0 — JOSS Submission Release

> Event-driven power grid simulation with auto-switching decision system.

## What's New in v1.0.0

This is the first stable release of PowerGridSim, submitted to the
**Journal of Open Source Software (JOSS)**.

### Features

**Phase 1: Event-Driven Simulation**
- Six event types: load_add, load_drop, gen_trip, gen_commit, line_trip, line_close
- Snapshot-based state tracking with bus voltages, line loadings, generator outputs
- Zero-delay rule evaluation (re-PF after rule action)

**Phase 2: Topology Control**
- 5-bus radial feeder test system with switchable line topology
- Line + active flag pattern for switch modeling (more flexible than VeraGrid's Switch class)

**Phase 3: Rule Engine**
- Four default protection rules: UVLS, OVGR, OVERLOAD, RECONFIGURE
- Cooldown mechanism prevents rule oscillation
- YAML-based rule configuration (no code changes needed)

**Phase B: Realistic Load Modeling**
- ZIP model (constant impedance / current / power)
- Flicker modulation for inverter/VFD loads
- Stochastic on/off switching via discrete-time Markov chains

**Phase 4: Rule Generation**
- RuleSpec data model with materialize()
- Candidate enumerators for UVLS / OVGR / OVERLOAD / RECONF
- Simulation-based scoring with composite ranking metric
- Compound rule evaluation

**Phase 5: Visualization**
- Plotly single-file HTML dashboard
- Topology animation with time slider
- Dash-based real-time dashboard (auto-refresh every second)

**Phase A: YAML Configuration**
- Rules loaded from `config/rules.yaml`
- Hot-swap rule sets without modifying Python code

**Phase C: Topology-Aware Reconfiguration**
- Automatic tie-switch identification via BFS
- Fault isolation: open sectionalizer before closing tie
- Auto-derived tie_map (no hardcoded mapping)

**Phase D: Reinforcement Learning**
- Gymnasium-compatible `RadialFeederEnv`
- Stable-Baselines3 PPO integration
- Saved trained models

**Phase E: Probabilistic Power Flow**
- Monte Carlo with Gaussian load perturbations
- Voltage and loading violation probabilities
- Statistical reports with 5%/95% quantiles

**Phase F: Real-Time Dashboard**
- Dash server with interval callbacks
- Background simulation thread
- Live topology and time-series updates

### Test Suite

- **64 pytest tests** across 7 test modules
- All tests pass on Python 3.10 / 3.11 / 3.12
- Coverage of all core modules

### Documentation

- `README.md` — Quick start, installation, examples
- `docs/DESIGN.md` — Detailed design document (370+ lines)
- `paper.md` — JOSS submission paper
- `SUBMISSION_GUIDE.md` — Submission process guide
- Inline docstrings on every public function

### Tested Test Systems

- IEEE 14-bus (transmission, meshed)
- 5-bus radial feeder (distribution, with TIE switching)
- IEEE 30/57/118/300 (available in `Grids_and_profiles/`)
- Kundur two-area (RMS dynamic)

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from event_sim import Simulator, make_schedule
from rules_loader import load_engine_from_yaml
import VeraGridEngine as vg

grid = vg.open_file("Grids_and_profiles/grids/IEEE 14 bus.raw")
schedule = make_schedule(
    (10.0, "load_add", "BUS 14", 50.0),
    (40.0, "gen_trip", "2_1"),
)
engine = load_engine_from_yaml("lab_scripts/config/rules.yaml")
df = Simulator(grid, dt=1.0).run(duration=90.0, schedule=schedule, rules=engine)
```

## Validation

| Metric | Value |
|---|---|
| Total commits | 13+ |
| Lines of code | ~4500 |
| Test cases | 64 passing |
| Demo scripts | 14 (exp01–exp14) |
| Phase coverage | 12 (Phase 1-5 + B + A-F) |

## License

MIT License — see `LICENSE` for details.

## Citation

```bibtex
@software{powergridsim2026,
  author = {liu, ka},
  title = {PowerGridSim: Event-Driven Grid Simulation with Auto-Switching Decision System},
  year = {2026},
  journal = {Journal of Open Source Software}
}
```

## Zenodo DOI

(To be generated via GitHub Release → Zenodo integration)
