"""Property-based simulator determinism (Commit 8 §39, corrected §2.2)."""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulator.harness import run_scenario
from simulator.scenarios import ALL_SCENARIOS, build_all_scenarios

pytestmark = pytest.mark.property

_names = [s.name for s in build_all_scenarios()]


@given(st.sampled_from(_names))
@settings(max_examples=len(ALL_SCENARIOS) * 2, deadline=None)
def test_same_scenario_same_journal_bytes(name: str) -> None:
    scenario = next(s for s in build_all_scenarios() if s.name == name)
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        r1 = run_scenario(scenario, Path(d1))
        r2 = run_scenario(scenario, Path(d2))
        h1 = hashlib.sha256(r1.journalPath.read_bytes()).hexdigest()
        h2 = hashlib.sha256(r2.journalPath.read_bytes()).hexdigest()
        assert h1 == h2


@given(st.sampled_from(_names))
@settings(max_examples=len(ALL_SCENARIOS), deadline=None)
def test_synthetic_records_have_provenance(name: str) -> None:
    scenario = next(s for s in build_all_scenarios() if s.name == name)
    with tempfile.TemporaryDirectory() as d:
        result = run_scenario(scenario, Path(d))
        prov = result.provenance
        assert prov.usedRealHumanData is False
        assert prov.seed == scenario.defaultSeed
        assert prov.profileId
        assert prov.domain.value == "SYNTHETIC_SIMULATION"


@given(st.sampled_from(_names))
@settings(max_examples=len(ALL_SCENARIOS), deadline=None)
def test_scenario_input_profile_not_mutated(name: str) -> None:
    scenario = next(s for s in build_all_scenarios() if s.name == name)
    before = scenario.profile.model_dump(mode="json")
    with tempfile.TemporaryDirectory() as d:
        run_scenario(scenario, Path(d))
    assert scenario.profile.model_dump(mode="json") == before


@given(st.sampled_from(_names), st.integers(min_value=1, max_value=10_000))
@settings(max_examples=12, deadline=None)
def test_explicit_seed_is_deterministic(name: str, seed: int) -> None:
    """Same scenario + same explicit CLI seed → identical journal bytes (§2.2)."""
    scenario = next(s for s in build_all_scenarios() if s.name == name)
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        r1 = run_scenario(scenario, Path(d1), seed=seed)
        r2 = run_scenario(scenario, Path(d2), seed=seed)
        assert r1.seed == seed and r2.seed == seed
        assert r1.journalSha256 == r2.journalSha256
        assert [o.actualSpeedMps for o in r1.observations] == [
            o.actualSpeedMps for o in r2.observations
        ]
