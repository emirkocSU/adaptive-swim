"""Adaptive Swim headless simulator (Commit 8).

Embeds the production runtime (session aggregate, pacing/ghost engine, persistence, replay)
to produce deterministic, replayable session journals from virtual swimmers. It NEVER
re-implements domain logic and is never imported by ``swimcore``, ``contracts`` or
``persistence`` — the dependency arrow points only inward.
"""

from simulator.harness import (
    ScenarioStop,
    SimulationResult,
    SimulationScenario,
    ghost_wall_targets,
    run_scenario,
)
from simulator.provenance import SimulationProvenance, build_provenance
from simulator.scenarios import ALL_SCENARIOS, SCENARIO_BY_NAME, build_all_scenarios
from simulator.virtual_swimmer import (
    SwimmerBehaviour,
    SwimmerStopEvent,
    VirtualSwimResult,
    WallTouch,
    swim_walls,
)

__all__ = [
    "ALL_SCENARIOS",
    "SCENARIO_BY_NAME",
    "ScenarioStop",
    "SimulationProvenance",
    "SimulationResult",
    "SimulationScenario",
    "SwimmerBehaviour",
    "SwimmerStopEvent",
    "VirtualSwimResult",
    "WallTouch",
    "build_all_scenarios",
    "build_provenance",
    "ghost_wall_targets",
    "run_scenario",
    "swim_walls",
]
