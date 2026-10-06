---
title: 'PowerGridSim: Event-Driven Grid Simulation with Auto-Switching Decision System'
tags:
  - power-systems
  - simulation
  - distribution-automation
  - rule-engine
  - probabilistic-power-flow
  - reinforcement-learning
  - python
authors:
  - name: liuka
    orcid:
    affiliation:
affiliations:
  - name: Independent Researcher
    index: 1
date: 6 October 2026
bibliography: paper.bib
---

# Summary

PowerGridSim is an event-driven power grid simulation platform built on
[VeraGrid](https://github.com/SanPen-Alcon/VeraGrid). It provides a unified
Python interface for simulating grid disturbances (load changes, generator
trips, line faults), automatically generating and evaluating protection
rules, and visualizing grid state evolution through interactive dashboards.

The software targets researchers studying distribution automation,
self-healing grids, and reinforcement learning for power systems. It includes:

- An event-driven simulator with six event types and snapshot/state tracking
- A topology-aware rule engine with four default protection rules
- A rule generation framework that enumerates candidate IF-THEN policies and
  ranks them by simulation-based scoring
- A probabilistic power flow module for Monte Carlo evaluation under load
  uncertainty
- An interactive HTML dashboard (Plotly) and a real-time Dash server
- A Gymnasium-compatible reinforcement learning environment
- A library of seven benchmark scenarios and a 64-test pytest suite

# Statement of Need

Power system automation research requires tools that go beyond steady-state
analysis: researchers need to model transient disturbances, evaluate
protective relaying logic, and study how topologies reconfigure after faults.
Existing commercial and open-source simulators (PSS/E, DIgSILENT
PowerFactory, OpenDSS, GridCal) excel at numerical analysis but typically do
not provide:

- A unified Python API for event-driven simulation (load add/drop, generator
  trip, line trip) at user-defined time steps
- Built-in rule engines with cooldown mechanisms that prevent oscillation
- Topology-aware auto-reconfiguration with fault isolation
- Probabilistic power flow integrated with the same event-driven simulator
- Interactive web dashboards for live visualization
- A reinforcement learning environment that wraps the same simulator

PowerGridSim addresses these gaps by providing an end-to-end Python workflow
that combines simulation, rule evaluation, statistical analysis, and
visualization in a single package. It targets researchers who need to
prototype protection strategies, benchmark control algorithms, and produce
reproducible visualizations without writing low-level solver code.

The software is built on top of VeraGrid's power flow solver, inheriting its
performance and accuracy for the underlying AC network equations while
providing a higher-level workflow tailored to distribution automation
research.

# Software Functionality

## Core Modules

### Event-Driven Simulator (`event_sim.py`)

Defines six event types — `load_add`, `load_drop`, `gen_trip`,
`gen_commit`, `line_trip`, `line_close` — and a `Simulator` class that runs
power flow at each time step, applies pending events, evaluates rules,
and emits snapshot records. The simulator supports a configurable time
step `dt`, a fault tracker for tracking recent line trips, and an optional
profiler for time-varying loads. After rule actions fire, the simulator
re-runs power flow to make actions immediately visible (zero-delay
optimization), eliminating the one-step delay seen in earlier designs.

### Rule Engine (`rule_engine.py`)

Provides a `Rule` dataclass with a `when(state, grid) -> bool` predicate
and a `then(grid, state) -> str` action, plus a `RuleEngine` scheduler
with cooldown control and a log of firing events. Four default rules are
provided:

- `R001_UVLS` — under-voltage load shedding (`V < 0.93 pu → shed 30%` of load
  on the worst bus)
- `R002_OVGR` — over-voltage generation reduction (`V > 1.10 pu →
  reduce generator output 20%`)
- `R003_OVERLOAD` — overload load shedding (`line loading > 130% →
  shed 10%` of load at the receiving bus)
- `R004_RECONFIGURE` — automatic reconfiguration (detect blackout,
  close tie switch, with optional fault isolation)

Rules can be defined in code or loaded from YAML configuration files.

### Topology Analysis (`topology_analyzer.py`)

Provides BFS-based path-to-source search, automatic tie-switch
identification, and tie_map construction for automatic reconfiguration.
The `find_fault_isolation_switch` function identifies the appropriate
sectionalizer to open when a fault is detected, enabling fault-tolerant
reconfiguration.

### Rule Generation (`rule_generator.py`)

Implements the `RuleSpec` data model with `materialize`, candidate
generators for UVLS / OVGR / OVERLOAD / RECONF, and scoring functions
based on `min_v`, `max_load`, blackout duration, and losses. The
`run_search` function evaluates all candidate rules in a scenario and
ranks them by composite score.

### Realistic Load Modeling (`load_profiles.py`)

Implements the ZIP load model (constant impedance, constant current,
constant power), flicker modulation (`P(t) = P_base · (1 + A·sin(2π·f·t))`),
and stochastic on/off switching via discrete-time Markov chains. Three
preset templates (`industrial_factory`, `vfd_load`, `residential`) cover
common load types in distribution networks.

### Visualization (`dashboard.py`, `exp14_dash_live.py`)

`dashboard.py` builds interactive Plotly figures — topology graphs colored
by bus voltage and line loading, time-series plots with event markers,
and an animated topology evolution plot. `exp14_dash_live.py` starts a Dash
server that refreshes the topology and time-series plots every second as a
background simulation thread runs.

### Probabilistic Power Flow (`exp13_ppf.py`)

Runs Monte Carlo simulations with Gaussian load perturbations to compute
probability distributions of bus voltages and line loadings, including
violation probabilities (e.g., `P(V < 0.95)` and `P(loading > 100%)`).

### Reinforcement Learning (`rl_env.py`, `exp12_rl_train.py`)

Defines a Gymnasium environment (`RadialFeederEnv`) where the agent
controls a tie switch and receives reward based on feeder recovery.
Stable-Baselines3 PPO is provided as a baseline learning algorithm.

## Benchmark Scenarios (`scenarios.py`)

A library of seven pre-defined test scenarios including N-1 line trips, N-1
generator trips, load steps, cascading faults, and feeder-side faults with
recovery. `exp10_benchmark.py` runs all scenarios against the YAML-loaded
rule set and reports pass/fail with detailed metrics.

## Test Suite

The package includes 64 pytest tests in the `tests/` directory covering
event injection, simulator loop, rule engine, topology analysis, load
profiles, rule generation, and YAML loading. Tests are run with:

```bash
pytest
```

## Example Usage

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
sim = Simulator(grid, dt=1.0)
df = sim.run(duration=90.0, schedule=schedule, rules=engine)
```

# Similar Work

[VeraGrid](https://github.com/SanPen-Alcon/VeraGrid) and its predecessor
[GridCal](https://github.com/SanPen-Alcon/GridCal) provide the underlying
power flow solver but do not include event injection, rule engines, or
visualization dashboards. PowerGridSim builds on VeraGrid's solver to add
these higher-level capabilities.

[PyPSA](https://github.com/PyPSA/PyPSA) is a Python toolbox for
simulating and optimizing modern power systems but focuses on scenario
optimization rather than event-driven simulation and rule-based
protection.

[OpenDSS](https://sourceforge.net/projects/electricdss/) is a distribution
system simulator with extensive model libraries but lacks Python
integration and rule engines.

PowerGridSim's distinguishing features are: (1) a single Python workflow
combining event-driven simulation, rule engines, and visualization; (2)
topology-aware auto-reconfiguration with fault isolation; and (3)
integrated probabilistic power flow and reinforcement learning
environments.

# Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Event Injection    ──►  Simulator  ──►  Snapshot       │
│ (load/gen/line     (VeraGrid PF +   (V, load, P,      │
│  events)           rule evaluation)   topology, loss)   │
└─────────────────────────────────────────────────────────┘
                ▲                            │
                │                            ▼
        ┌───────┴────────┐         ┌─────────────────┐
        │ Rule Engine    │         │ Visualization   │
        │ (UVLS/OVGR/OVL/│         │ (Plotly HTML +  │
        │  RECONF)       │         │  Dash live)     │
        └────────────────┘         └─────────────────┘
```

# Research Applications

The software has been used to:

1. Validate that rule-based protection reduces minimum voltage by 0.010 pu
   and line loading by 15% on IEEE 14 under cascading faults
2. Demonstrate that topology-aware reconfiguration reduces feeder
   blackout from 25 steps to 1 step on a 5-bus radial feeder
3. Quantify probabilistic risk: line `1_2_1` on IEEE 14 has 79.5%
   overload probability under ±10% load perturbations
4. Provide a Gymnasium environment for training reinforcement learning
   agents on distribution automation

# Acknowledgements

The author thanks the VeraGrid development team for providing the
underlying power system solver and the VeraGrid community for API
support.

# References

VeraGrid: <https://github.com/SanPen-Alcon/VeraGrid>

Plotly: <https://plotly.com/>

Dash: <https://dash.plotly.com/>

Stable-Baselines3: <https://stable-baselines3.readthedocs.io/>

IEEE 14-bus test system: <https://power-grid-lib.readthedocs.io/>

Kundur two-area system: Kundur, P. (1994). *Power System Stability and
Control*. McGraw-Hill.
