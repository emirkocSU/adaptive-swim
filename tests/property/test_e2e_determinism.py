"""Property-based determinism of the Phase 1 vertical slice (ADR-041 §19)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from e2e.cases import CASE_BY_ID
from e2e.runner import deterministic_run_id, run_phase1_vertical_slice

_FAST_CASES = ("normal-continuous-completion", "stop-during-planned-rest")


@given(st.sampled_from(_FAST_CASES), st.integers(min_value=1, max_value=5_000))
@settings(max_examples=3, deadline=None)
def test_same_case_and_seed_produce_identical_artifacts(case_id: str, seed: int) -> None:
    case = CASE_BY_ID[case_id]()
    with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
        first = run_phase1_vertical_slice(
            case=case, output_directory=Path(first_dir) / "bundle", seed=seed
        )
        second = run_phase1_vertical_slice(
            case=CASE_BY_ID[case_id](),
            output_directory=Path(second_dir) / "elsewhere" / "bundle",
            seed=seed,
        )
        assert first.runId == second.runId
        assert first.verificationManifest.manifestId == second.verificationManifest.manifestId
        assert first.journalPath.read_bytes() == second.journalPath.read_bytes()
        assert first.sessionReportPath.read_bytes() == second.sessionReportPath.read_bytes()
        assert (
            first.verificationManifestPath.read_bytes()
            == second.verificationManifestPath.read_bytes()
        )


@given(
    st.text(min_size=1, max_size=12),
    st.integers(min_value=0, max_value=10_000),
    st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
)
@settings(max_examples=25, deadline=None)
def test_run_id_is_a_deterministic_pure_hash(case_id: str, seed: int, digest: str) -> None:
    material = {
        "case_id": case_id,
        "case_version": "1.0.0",
        "seed": seed,
        "workout_digest": digest,
        "source_workout_digest": None,
        "profile_digests": {"profile:1": digest},
        "selected_profile_id": "profile",
        "selected_profile_version": "1",
        "replacement_profile_id": None,
        "replacement_profile_version": None,
        "scenario_version": "2.0.0",
        "scenario_digest": digest,
        "analytics_policy_digest": digest,
        "runner_version": "e2e-runner-1.1.0",
    }
    value = deterministic_run_id(**material)
    assert value == deterministic_run_id(**material)
    assert len(value) == 64
    assert value != deterministic_run_id(**{**material, "seed": seed + 1})
