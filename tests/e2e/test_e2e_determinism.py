"""Determinism of the Phase 1 vertical slice (ADR-041 §5)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from e2e.cases import CASE_BY_ID
from e2e.runner import deterministic_run_id, run_phase1_vertical_slice
from e2e.types import E2E_RUNNER_VERSION, Phase1E2EResult

CASE = "normal-continuous-completion"


def test_same_case_same_seed_is_byte_identical(
    run_case: Callable[..., Phase1E2EResult], e2e_root: Path
) -> None:
    first = run_case(CASE, seed=42, label="det-a")
    second = run_case(CASE, seed=42, label="det-b")
    assert first.bundleDirectory != second.bundleDirectory
    assert first.runId == second.runId
    assert first.journalSha256 == second.journalSha256
    assert first.sessionReportSha256 == second.sessionReportSha256
    assert first.verificationManifestSha256 == second.verificationManifestSha256
    assert first.verificationManifest.manifestId == second.verificationManifest.manifestId
    for name in (
        "journal.jsonl",
        "session-report.json",
        "command-outcomes.json",
        "artifact-sha256.txt",
        "manifest.json",
    ):
        assert (first.bundleDirectory / name).read_bytes() == (
            second.bundleDirectory / name
        ).read_bytes()


def test_output_path_does_not_affect_artifact_bytes(
    run_case: Callable[..., Phase1E2EResult], e2e_root: Path
) -> None:
    first = run_case(CASE, seed=7, label="path-one")
    nested = run_phase1_vertical_slice(
        case=CASE_BY_ID[CASE](),
        output_directory=e2e_root / "deeply" / "nested" / "elsewhere",
        seed=7,
    )
    assert first.verificationManifestSha256 == nested.verificationManifestSha256
    assert first.journalSha256 == nested.journalSha256
    assert first.sessionReportSha256 == nested.sessionReportSha256
    assert first.verificationManifest.artifactDigests == nested.verificationManifest.artifactDigests
    assert first.verificationManifest.artifactDigestFileSha256 == (
        nested.verificationManifest.artifactDigestFileSha256
    )


def test_a_different_seed_changes_the_run(run_case: Callable[..., Phase1E2EResult]) -> None:
    base = run_case(CASE, seed=42, label="seed-42")
    other = run_case(CASE, seed=99, label="seed-99")
    assert base.runId != other.runId
    assert base.journalSha256 != other.journalSha256
    assert base.verificationManifest.manifestId != other.verificationManifest.manifestId
    # domain invariants hold regardless of the seed
    for result in (base, other):
        assert result.allChecksPassed
        assert result.replayFinalState.officialCompletedDistanceM == 100.0


def test_run_id_is_a_pure_function_of_identity() -> None:
    material = {
        "case_id": "normal-continuous-completion",
        "case_version": "1.0.0",
        "seed": 42,
        "workout_digest": "a" * 64,
        "source_workout_digest": None,
        "profile_digests": {"profile:1": "b" * 64},
        "selected_profile_id": "profile",
        "selected_profile_version": "1",
        "replacement_profile_id": None,
        "replacement_profile_version": None,
        "scenario_version": "2.0.0",
        "scenario_digest": "c" * 64,
        "analytics_policy_digest": "d" * 64,
        "runner_version": E2E_RUNNER_VERSION,
    }
    first = deterministic_run_id(**material)
    assert first == deterministic_run_id(**material)
    assert len(first) == 64
    assert first != deterministic_run_id(**{**material, "seed": 43})
    assert first != deterministic_run_id(**{**material, "workout_digest": "c" * 64})
    assert first != deterministic_run_id(
        **{**material, "runner_version": f"{E2E_RUNNER_VERSION}-next"}
    )


def test_no_wall_clock_or_uuid_in_the_run_identity(
    run_case: Callable[..., Phase1E2EResult],
) -> None:
    result = run_case(CASE)
    expected = deterministic_run_id(
        case_id=result.caseId,
        case_version=result.caseVersion,
        seed=result.seed,
        workout_digest=result.workoutDigest,
        source_workout_digest=result.sourceWorkoutDigest,
        profile_digests=result.profileDigests,
        selected_profile_id=CASE_BY_ID[CASE]().scenario.profile.profileId,
        selected_profile_version=CASE_BY_ID[CASE]().scenario.profile.profileVersion,
        replacement_profile_id=None,
        replacement_profile_version=None,
        scenario_version=CASE_BY_ID[CASE]().scenario.scenarioVersion,
        scenario_digest=result.scenarioDigest,
        analytics_policy_digest=result.analyticsPolicyDigest,
        runner_version=E2E_RUNNER_VERSION,
    )
    assert result.runId == expected


def test_run_id_covers_profiles_replacement_and_analytics_policy() -> None:
    material = {
        "case_id": "coach-profile-reset",
        "case_version": "1.0.0",
        "seed": 42,
        "workout_digest": "a" * 64,
        "source_workout_digest": None,
        "profile_digests": {
            "resetbase100:1": "b" * 64,
            "resetrepl100:1": "c" * 64,
        },
        "selected_profile_id": "resetbase100",
        "selected_profile_version": "1",
        "replacement_profile_id": "resetrepl100",
        "replacement_profile_version": "1",
        "scenario_version": "2.0.0",
        "scenario_digest": "d" * 64,
        "analytics_policy_digest": "e" * 64,
        "runner_version": E2E_RUNNER_VERSION,
    }
    base = deterministic_run_id(**material)
    changed_replacement = dict(material)
    changed_replacement["profile_digests"] = {
        **material["profile_digests"],
        "resetrepl100:1": "f" * 64,
    }
    changed_policy = {**material, "analytics_policy_digest": "0" * 64}
    assert deterministic_run_id(**changed_replacement) != base
    assert deterministic_run_id(**changed_policy) != base
