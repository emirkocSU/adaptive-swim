"""Adaptive Swim headless simulator (Commit 8, corrected).

Embeds the production runtime (session aggregate, pacing/ghost engine, persistence, replay)
to produce deterministic, replayable session journals from a tick-based virtual swimmer. It
NEVER re-implements domain logic and is never imported by ``swimcore``, ``contracts`` or
``persistence`` — the dependency arrow points only inward. It also never reads a raw
dataset and never performs model inference.
"""

from simulator.harness import (
    CommandOutcome,
    GhostSnapshot,
    LiveFinalState,
    ScenarioStop,
    SimulationError,
    SimulationResult,
    SimulationScenario,
    SwimmerParams,
    ghost_wall_targets,
    run_scenario,
)
from simulator.provenance import (
    SimulationProvenance,
    SimulationRunManifest,
    build_provenance,
    build_run_manifest,
    deterministic_run_id,
)
from simulator.scenarios import (
    ALL_SCENARIOS,
    DEMO_SCENARIOS,
    REQUIRED_SCENARIO_NAMES,
    REQUIRED_SCENARIOS,
    SCENARIO_BY_NAME,
    build_all_scenarios,
)
from simulator.virtual_swimmer import (
    RestWindow,
    StopWindow,
    SwimmerBehaviour,
    SwimmerObservation,
    UnreliableWindow,
    VirtualSwimmerConfig,
    VirtualSwimResult,
    WallTouch,
    simulate_swim,
    swim_walls,
)

__all__ = [
    "ALL_SCENARIOS",
    "DEMO_SCENARIOS",
    "REQUIRED_SCENARIOS",
    "REQUIRED_SCENARIO_NAMES",
    "SCENARIO_BY_NAME",
    "CommandOutcome",
    "GhostSnapshot",
    "LiveFinalState",
    "RestWindow",
    "ScenarioStop",
    "SimulationError",
    "SimulationProvenance",
    "SimulationResult",
    "SimulationRunManifest",
    "SimulationScenario",
    "StopWindow",
    "SwimmerBehaviour",
    "SwimmerObservation",
    "SwimmerParams",
    "UnreliableWindow",
    "VirtualSwimResult",
    "VirtualSwimmerConfig",
    "WallTouch",
    "build_all_scenarios",
    "build_provenance",
    "build_run_manifest",
    "deterministic_run_id",
    "ghost_wall_targets",
    "run_scenario",
    "simulate_swim",
    "swim_walls",
]
