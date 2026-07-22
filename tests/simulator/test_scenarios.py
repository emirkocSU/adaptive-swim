"""Simulator scenario regression tests against the real core (Commit 8, corrected §15).

Covers the eight required acceptance scenarios, the absence of alias shortcuts, real seed
plumbing, harness-internal replay validation, replacement-profile metadata in live AND
replay state, and simulation provenance completeness.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from persistence import JsonlSessionEventLog
from simulator.harness import run_scenario
from simulator.scenarios import (
    REQUIRED_SCENARIO_NAMES,
    SCENARIO_BY_NAME,
    build_all_scenarios,
)
from swimcore.replay import replay_session
from swimcore.session.state import SessionState

pytestmark = pytest.mark.simulator

_ALL_NAMES = [s.scenarioId for s in build_all_scenarios()]

_REQUIRED = (
    "normal-pace-loss",
    "long-stop-mid-length",
    "manual-stop-at-verified-wall",
    "duplicate-stop-mark",
    "stop-during-planned-rest",
    "unreliable-position-time",
    "complete-while-stop-paused",
    "coach-continuous-curve-reset",
)


def _run(name: str, tmp: Path, *, seed: int | None = None):  # noqa: ANN202
    scenario = SCENARIO_BY_NAME[name]()
    return run_scenario(scenario, tmp, seed=seed)


# --------------------------------------------------------------------------- registry
def test_all_eight_required_scenarios_exist() -> None:
    assert REQUIRED_SCENARIO_NAMES == _REQUIRED
    for name in _REQUIRED:
        assert name in SCENARIO_BY_NAME


def test_required_scenarios_are_not_aliases_of_demos() -> None:
    """Each required slug must build its OWN scenario, never redirect to a demo."""
    demo_ids = {"even-on-plan", "stop-pause", "coach-continuous-reset", "positive-fade"}
    for name in _REQUIRED:
        scenario = SCENARIO_BY_NAME[name]()
        assert scenario.scenarioId == name
        assert scenario.scenarioId not in demo_ids
    profile_ids = {SCENARIO_BY_NAME[n]().profile.profileId for n in _REQUIRED}
    assert len(profile_ids) == len(_REQUIRED)


# --------------------------------------------------------------------------- generic
@pytest.mark.parametrize("name", _ALL_NAMES)
def test_scenario_reaches_completed(name: str, tmp_path: Path) -> None:
    result = _run(name, tmp_path)
    log = JsonlSessionEventLog(result.journalPath, result.sessionId)
    replay = replay_session(list(log.read_all().events))
    assert replay.state.lifecycleState is SessionState.COMPLETED


@pytest.mark.parametrize("name", _ALL_NAMES)
def test_harness_validates_live_against_replay(name: str, tmp_path: Path) -> None:
    """§2.4: the harness itself re-reads the journal and compares live vs replay."""
    result = _run(name, tmp_path)
    assert result.replayMatchesLiveState
    st = result.replayResult.state
    live = result.liveFinalState
    assert live.selectedPaceProfileId == st.selectedPaceProfileId
    assert live.selectedPaceProfileSource == st.selectedPaceProfileSource
    assert live.profileCoachLocked == st.profileCoachLocked
    assert result.journalSha256


@pytest.mark.parametrize("name", _ALL_NAMES)
def test_official_distance_is_pool_multiple(name: str, tmp_path: Path) -> None:
    result = _run(name, tmp_path)
    st = result.replayResult.state
    assert st.officialCompletedDistanceM is not None
    assert st.officialCompletedDistanceM == st.officialCompletedLengthCount * st.poolLengthM


@pytest.mark.parametrize("name", _ALL_NAMES)
def test_observations_are_tick_based(name: str, tmp_path: Path) -> None:
    result = _run(name, tmp_path)
    assert len(result.observations) > 10
    obs = result.observations
    ticks = {obs[i + 1].wallTimeMs - obs[i].wallTimeMs for i in range(len(obs) - 1)}
    assert ticks == {100}


@pytest.mark.parametrize("name", _ALL_NAMES)
def test_simulation_provenance_is_complete(name: str, tmp_path: Path) -> None:
    result = _run(name, tmp_path)
    manifest = result.manifest
    assert manifest.synthetic is True
    assert manifest.scenarioId == result.scenarioId
    assert manifest.scenarioVersion
    assert manifest.seed == result.seed
    assert manifest.simulatorVersion and manifest.harnessVersion
    assert manifest.workoutRef == "w1"
    assert manifest.profileId and manifest.profileVersion
    assert manifest.compilerVersion
    assert len(manifest.runId) == 64
    prov = result.provenance
    assert prov.usedRealHumanData is False
    assert prov.licenseVerified is False
    assert prov.domain.value == "SYNTHETIC_SIMULATION"


def test_run_id_is_deterministic_and_seed_sensitive(tmp_path: Path) -> None:
    a = _run("normal-pace-loss", tmp_path / "a", seed=42)
    b = _run("normal-pace-loss", tmp_path / "b", seed=42)
    c = _run("normal-pace-loss", tmp_path / "c", seed=99)
    assert a.runId == b.runId
    assert a.runId != c.runId


# --------------------------------------------------------------------------- seed (§2.2)
def test_same_seed_same_journal_and_trace(tmp_path: Path) -> None:
    a = _run("normal-pace-loss", tmp_path / "a", seed=42)
    b = _run("normal-pace-loss", tmp_path / "b", seed=42)
    assert a.journalSha256 == b.journalSha256
    assert [o.actualSpeedMps for o in a.observations] == [o.actualSpeedMps for o in b.observations]


def test_different_seed_changes_observation_trace(tmp_path: Path) -> None:
    a = _run("normal-pace-loss", tmp_path / "a", seed=42)
    c = _run("normal-pace-loss", tmp_path / "c", seed=99)
    assert [o.actualSpeedMps for o in a.observations] != [o.actualSpeedMps for o in c.observations]
    for result in (a, c):
        st = result.replayResult.state
        assert st.lifecycleState is SessionState.COMPLETED
        assert st.officialCompletedDistanceM == 100.0
        assert st.stoppedDurationMs == 0


def test_registry_default_seed_is_used_without_cli_override(tmp_path: Path) -> None:
    scenario = SCENARIO_BY_NAME["normal-pace-loss"]()
    result = run_scenario(scenario, tmp_path)
    assert result.seed == scenario.defaultSeed == 42


# --------------------------------------------------------------------------- NORMAL_PACE_LOSS
def test_normal_pace_loss_creates_and_keeps_a_real_gap(tmp_path: Path) -> None:
    result = _run("normal-pace-loss", tmp_path)
    gaps = [o.gapM for o in result.observations]
    assert gaps[0] <= 0.5
    assert max(gaps) > 2.0, "the swimmer must genuinely fall behind the target curve"
    # the gap must GROW and persist while the ghost is still running (it necessarily
    # collapses to zero only after the ghost has reached the finish and stops advancing)
    running = [
        o.gapM
        for o in result.observations
        if 0.0 < o.targetDistanceM < result.wallCount * 25 - 1e-6
    ]
    assert running[-1] > running[0]
    assert min(running[len(running) // 2 :]) > 1.0, "the gap must persist, not close"
    # the swimmer finishes behind the plan: every wall is reached after its ghost target
    assert all(s.swimmerGapMsAtWall > 0 for s in result.ghostSnapshots)
    assert not any("StopPause" in e.type.value for e in result.events)
    st = result.replayResult.state
    assert st.stoppedDurationMs == 0
    assert st.activeDurationMs > 0


def test_normal_pace_loss_profile_uses_dataset_evidence_provenance(tmp_path: Path) -> None:
    """§13: at least one continuous scenario profile carries the ADR-039 provenance."""
    scenario = SCENARIO_BY_NAME["normal-pace-loss"]()
    prov = scenario.profile.curveProvenance
    assert prov.curveOrigin is not None
    assert prov.curveOrigin.value == "RACE_PRIOR_TRAINING_CORRECTED"
    assert prov.curveEvidenceLevel is not None
    assert prov.curveEvidenceLevel.value == "COARSE_SPLIT_DERIVED"
    assert prov.visualShapeSource is not None
    assert prov.visualShapeSource.value == "BOUNDED_TEMPLATE"
    assert prov.continuousCurveGroundTruth is False
    result = _run("normal-pace-loss", tmp_path)
    assert result.manifest.synthetic is True


# --------------------------------------------------------------------------- LONG_STOP
def test_long_stop_is_retroactive_and_reconciles_once(tmp_path: Path) -> None:
    result = _run("long-stop-mid-length", tmp_path)
    st = result.replayResult.state
    assert len(st.completedStopPauses) == 1
    interval = st.completedStopPauses[0]
    started_events = [e for e in result.events if e.type.value == "StopPauseStarted"]
    assert len(started_events) == 1
    assert interval.startedAtMs < started_events[0].tsMs - 1000
    assert st.stoppedDurationMs == 15_000
    assert st.officialCompletedDistanceM == 100.0
    assert st.wallReconciliationPending is False


# --------------------------------------------------------------------------- MANUAL_STOP
def test_manual_stop_aligns_at_the_official_wall(tmp_path: Path) -> None:
    result = _run("manual-stop-at-verified-wall", tmp_path)
    started = [e for e in result.events if e.type.value == "StopPauseStarted"]
    assert len(started) == 1
    payload = started[0].payload
    assert payload.trigger.value == "MANUAL_INCIDENT"
    assert payload.detectionSource.value == "COACH"
    assert payload.alignmentSource.value == "COACH_MARK"
    scenario = SCENARIO_BY_NAME["manual-stop-at-verified-wall"]()
    assert scenario.stop is not None
    assert scenario.stop.trackedAlignmentDistanceM % scenario.workout.poolLengthM == 0
    st = result.replayResult.state
    assert st.lifecyclePausedDurationMs == 0
    assert st.stoppedDurationMs == 12_000
    assert not any(e.type.value in ("SessionPaused", "SessionResumed") for e in result.events)


# --------------------------------------------------------------------------- DUPLICATE_MARK
def test_duplicate_stop_mark_produces_no_second_event_or_batch(tmp_path: Path) -> None:
    result = _run("duplicate-stop-mark", tmp_path)
    marks = [o for o in result.commandOutcomes if o.commandType == "MarkStopPause"]
    assert len(marks) == 2
    assert marks[0].outcome == "APPLIED" and marks[0].eventCount > 0
    assert marks[1].outcome == "IDEMPOTENT_REPLAY" and marks[1].eventCount == 0
    started = [e for e in result.events if e.type.value == "StopPauseStarted"]
    assert len(started) == 1
    st = result.replayResult.state
    assert len(st.completedStopPauses) == 1
    lines = [line for line in result.journalPath.read_bytes().split(b"\n") if line.strip()]
    assert len(lines) == len(result.eventBatches)


# --------------------------------------------------------------------------- PLANNED REST
def test_planned_rest_creates_no_stop_pause(tmp_path: Path) -> None:
    result = _run("stop-during-planned-rest", tmp_path)
    assert not any("StopPause" in e.type.value for e in result.events)
    st = result.replayResult.state
    assert st.stoppedDurationMs == 0
    assert st.lifecyclePausedDurationMs == 0
    rest_ticks = [o for o in result.observations if o.plannedRest]
    assert len(rest_ticks) >= 100
    assert all(o.actualSpeedMps == 0.0 for o in rest_ticks)


# --------------------------------------------------------------------------- UNRELIABLE
def test_unreliable_position_stays_visual_only(tmp_path: Path) -> None:
    result = _run("unreliable-position-time", tmp_path)
    low = [o for o in result.observations if o.positionQuality == "LOW"]
    assert low, "the scenario must actually degrade position confidence"
    st = result.replayResult.state
    assert st.officialCompletedDistanceM == 100.0
    assert st.officialCompletedLengthCount == 4
    splits = [e for e in result.events if e.type.value == "SplitRecorded"]
    assert len(splits) == 4
    # official distance is derived from pool geometry, never from the noisy estimate
    for recorded in st.recordedSplits:
        assert recorded.officialDistanceM is not None
        assert recorded.officialDistanceM % 25 == 0
    assert st.stoppedDurationMs == 0


# --------------------------------------------------------------------------- COMPLETE WHILE STOPPED
def test_complete_is_rejected_while_stop_paused_then_succeeds(tmp_path: Path) -> None:
    result = _run("complete-while-stop-paused", tmp_path)
    assert result.completeRejectedWhileStopPaused
    rejected = [o for o in result.commandOutcomes if o.outcome == "REJECTED"]
    assert len(rejected) == 1
    assert rejected[0].commandType == "CompleteSession"
    assert rejected[0].eventCount == 0
    completed = [e for e in result.events if e.type.value == "SessionCompleted"]
    assert len(completed) == 1
    st = result.replayResult.state
    assert st.lifecycleState is SessionState.COMPLETED
    assert "complete-early" not in st.processedClientCommandIds


# --------------------------------------------------------------------------- COACH RESET
def test_coach_curve_reset_swaps_all_profile_metadata(tmp_path: Path) -> None:
    result = _run("coach-continuous-curve-reset", tmp_path)
    assert result.replacementInjected
    requested = [e for e in result.events if e.type.value == "CoachPacingResetRequested"]
    applied = [e for e in result.events if e.type.value == "CoachPacingResetApplied"]
    assert len(requested) == 1 and len(applied) == 1
    split_events = [e for e in result.events if e.type.value == "SplitRecorded"]
    wall_times = [e.tsMs for e in split_events]
    # requested mid-length between the 50 m and 75 m walls, applied at the 75 m wall
    assert wall_times[1] < requested[0].tsMs < wall_times[2]
    assert applied[0].payload.effectiveFromLength == 2

    payload = applied[0].payload
    assert payload.replacementPaceProfileId == "resetrepl100"
    assert payload.replacementPaceProfileSource == "COACH_APPROVED_MODEL"
    assert payload.replacementProfileCoachLocked is True
    assert payload.replacementCurveRepresentation == "PCHIP"
    assert payload.replacementCurveCompilerVersion
    assert payload.replacementAppliedPaceSecPer100M is not None

    live = result.liveFinalState
    assert live.selectedPaceProfileId == "resetrepl100"
    assert live.selectedPaceProfileSource == "COACH_APPROVED_MODEL"
    assert live.profileCoachLocked is True
    assert live.selectedCurveRepresentation == "PCHIP"
    assert live.selectedProfileTargetTotalTimeSec == pytest.approx(100.0)

    st = result.replayResult.state
    assert st.selectedPaceProfileId == "resetrepl100"
    assert st.selectedPaceProfileSource == "COACH_APPROVED_MODEL"
    assert st.selectedPaceProfileType == "CONTROLLED_START"
    assert st.profileCoachLocked is True
    assert st.selectedCurveRepresentation == "PCHIP"
    assert st.selectedProfileTargetTotalTimeSec == pytest.approx(100.0)
    assert st.appliedPaceSecPer100M == pytest.approx(payload.replacementAppliedPaceSecPer100M)
    assert st.stoppedDurationMs == 0
    assert len(st.recordedSplits) == 4
    assert [s.lengthIndex for s in st.recordedSplits] == [0, 1, 2, 3]


# --------------------------------------------------------------------------- misc
def test_uses_simulated_split_source(tmp_path: Path) -> None:
    result = _run("normal-pace-loss", tmp_path)
    splits = [e for e in result.events if e.type.value == "SplitRecorded"]
    assert splits
    for e in splits:
        assert e.payload.source.value == "SIMULATED"


def test_migrated_legacy_scenario_uses_constant_speed(tmp_path: Path) -> None:
    result = _run("migrated-legacy", tmp_path)
    assert result.provenance.curveRepresentation == "CONSTANT_SPEED"


def test_golden_journals_match(tmp_path: Path) -> None:
    """The committed simulator goldens equal freshly generated bytes."""
    golden_dir = Path(__file__).parent / "goldens"
    for name in ("normal-pace-loss", "long-stop-mid-length", "coach-continuous-curve-reset"):
        result = _run(name, tmp_path / name)
        committed = (golden_dir / f"{name}.jsonl").read_bytes()
        assert result.journalPath.read_bytes() == committed, f"{name} golden drifted"
