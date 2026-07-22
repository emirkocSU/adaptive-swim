"""The single authoritative Phase 1 cross-component invariant matrix (ADR-041).

Every check here compares outputs of *real* components against each other: the persisted
journal against the live aggregate, historical replay against live state, the compiled
target timeline against the approved profile, and the canonical report against the replay
state it was derived from. Nothing in this module recomputes domain logic — it only asserts
that the independently produced facts agree.

Checks are grouped exactly as the Phase 1 closure contract requires: event, state, clock,
distance, profile and report invariants, plus the case-specific expected outcome.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict

from analytics.identity import deterministic_report_id, event_digest_sha256
from analytics.serialization import encode_session_report
from analytics.types import ApprovedPaceProfileVersion
from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.event_log import EventBatchRecord
from contracts.events import EventEnvelope
from contracts.session_report import SessionReportV1_1
from contracts.workout import AnyWorkoutTemplate, WorkoutTemplateV1_1
from e2e.manifest import CheckStatus, Phase1VerificationCheck
from e2e.types import Phase1E2ECase
from simulator.harness import (
    CommandOutcome,
    LiveFinalState,
    SimulationResult,
    compile_ghost_timeline,
)
from swimcore.pacing.timeline import target_active_time_at_distance
from swimcore.pacing.types import PaceTimeline
from swimcore.replay.state import HistoricalSessionState
from swimcore.workout.start_mode import resolve_repeat_start_mode

_TOL = 1e-6

#: Tolerance for migration target equivalence. The 1.1 constant-speed representation is
#: evaluated through the continuous lookup grid, so only bounded floating/grid quantisation
#: may differ; total distance and target duration remain exact.
MIGRATION_TARGET_TOLERANCE_SEC = 0.005

#: Sampling step for the migration target-function comparison.
_MIGRATION_SAMPLE_STEP_M = 0.5


def _check(
    check_id: str,
    ok: bool,
    *,
    expected: object = None,
    actual: object = None,
    message: str | None = None,
) -> Phase1VerificationCheck:
    return Phase1VerificationCheck(
        checkId=check_id,
        status=CheckStatus.PASS if ok else CheckStatus.FAIL,
        expected=None if expected is None else str(expected),
        actual=None if actual is None else str(actual),
        message=message,
    )


def _skip(check_id: str, message: str) -> Phase1VerificationCheck:
    return Phase1VerificationCheck(
        checkId=check_id, status=CheckStatus.NOT_APPLICABLE, message=message
    )


def _profile_total_time(profile: ApprovedPaceProfileVersion) -> float:
    if isinstance(profile, ApprovedContinuousPaceProfile):
        return profile.targetTimeConstraint.targetTotalTimeSec
    return profile.targetTotalTimeSec


# --------------------------------------------------------------------------- event invariants
def check_event_invariants(
    events: Sequence[EventEnvelope],
    batches: Sequence[EventBatchRecord],
    journal_line_count: int,
) -> list[Phase1VerificationCheck]:
    checks: list[Phase1VerificationCheck] = []
    seqs = [event.seq for event in events]
    checks.append(
        _check("event.first_seq_is_one", bool(seqs) and seqs[0] == 1, expected=1, actual=seqs[:1])
    )
    contiguous = seqs == list(range(1, len(seqs) + 1))
    checks.append(
        _check(
            "event.seq_contiguous",
            contiguous,
            expected=f"1..{len(seqs)}",
            actual=f"{seqs[0] if seqs else None}..{seqs[-1] if seqs else None}",
        )
    )
    checks.append(
        _check(
            "event.seq_unique",
            len(set(seqs)) == len(seqs),
            expected=len(seqs),
            actual=len(set(seqs)),
        )
    )
    ids = [event.eventId for event in events]
    checks.append(
        _check(
            "event.id_unique_and_deterministic",
            len(set(ids)) == len(ids) and all(bool(value) for value in ids),
            expected="unique non-empty event ids",
            actual=f"{len(set(ids))}/{len(ids)} unique",
        )
    )
    non_decreasing = all(
        events[index].tsMs <= events[index + 1].tsMs for index in range(len(events) - 1)
    )
    checks.append(
        _check("event.timestamps_non_decreasing", non_decreasing, expected="monotonic tsMs")
    )
    single_session = len({event.sessionId for event in events}) == 1
    checks.append(_check("event.single_session_id", single_session, expected=1))

    batch_bounds_ok = all(
        batch.firstSeq == batch.events[0].seq
        and batch.lastSeq == batch.events[-1].seq
        and batch.eventCount == len(batch.events)
        for batch in batches
    )
    checks.append(_check("event.batch_bounds_correct", batch_bounds_ok))
    batch_seqs = [event.seq for batch in batches for event in batch.events]
    checks.append(
        _check(
            "event.batches_cover_stream",
            batch_seqs == seqs,
            expected=len(seqs),
            actual=len(batch_seqs),
        )
    )
    checks.append(
        _check(
            "event.journal_line_count_matches_batches",
            journal_line_count == len(batches),
            expected=len(batches),
            actual=journal_line_count,
        )
    )
    client_ids = [batch.clientCommandId for batch in batches]
    checks.append(
        _check(
            "event.no_duplicate_persisted_command",
            len(set(client_ids)) == len(client_ids),
            expected=len(client_ids),
            actual=len(set(client_ids)),
        )
    )
    return checks


# --------------------------------------------------------------------------- state invariants
def check_state_invariants(
    live: LiveFinalState, replay: HistoricalSessionState
) -> list[Phase1VerificationCheck]:
    pairs: list[tuple[str, object, object]] = [
        ("session_id", live.sessionId, replay.sessionId),
        ("lifecycle", live.lifecycleState, replay.lifecycleState.value),
        ("recorded_split_count", live.recordedSplitCount, len(replay.recordedSplits)),
        (
            "official_distance",
            live.officialCompletedDistanceM,
            replay.officialCompletedDistanceM,
        ),
        ("profile_id", live.selectedPaceProfileId, replay.selectedPaceProfileId),
        ("profile_version", live.selectedPaceProfileVersion, replay.selectedPaceProfileVersion),
        ("profile_source", live.selectedPaceProfileSource, replay.selectedPaceProfileSource),
        ("profile_type", live.selectedPaceProfileType, replay.selectedPaceProfileType),
        ("profile_coach_locked", live.profileCoachLocked, replay.profileCoachLocked),
        (
            "profile_target_total",
            live.selectedProfileTargetTotalTimeSec,
            replay.selectedProfileTargetTotalTimeSec,
        ),
        (
            "curve_representation",
            live.selectedCurveRepresentation,
            replay.selectedCurveRepresentation,
        ),
        (
            "curve_compiler_version",
            live.selectedCurveCompilerVersion,
            replay.selectedCurveCompilerVersion,
        ),
        ("open_stop_pause", live.openStopPause, replay.openStopPause is not None),
        (
            "pending_coach_reset",
            live.pendingCoachPacingReset,
            replay.pendingCoachPacingReset is not None,
        ),
    ]
    checks: list[Phase1VerificationCheck] = []
    for name, live_value, replay_value in pairs:
        if isinstance(live_value, float) and isinstance(replay_value, float):
            ok = abs(live_value - replay_value) <= _TOL
        else:
            ok = live_value == replay_value
        checks.append(
            _check(f"state.live_replay_{name}", ok, expected=live_value, actual=replay_value)
        )

    # Timing axes: the live ActiveClock totals must equal the independently replayed ones.
    timing_pairs: list[tuple[str, int | None, int]] = [
        ("active_duration", live.activeDurationMs, replay.activeDurationMs),
        ("stopped_duration", live.stoppedDurationMs, replay.stoppedDurationMs),
        ("wall_duration", live.wallElapsedMs, replay.wallDurationMs),
    ]
    for name, live_value, replay_value in timing_pairs:
        if live_value is None:
            checks.append(
                _skip(f"state.live_replay_{name}", "the live session clock never started")
            )
            continue
        checks.append(
            _check(
                f"state.live_replay_{name}",
                live_value == replay_value,
                expected=live_value,
                actual=replay_value,
            )
        )

    # Applied pace only exists in historical replay once an event carried it (a coach reset
    # or a control decision). Before that the replayed value is legitimately absent.
    if replay.appliedPaceSecPer100M is None:
        checks.append(
            _skip(
                "state.live_replay_applied_pace",
                "no event carried an applied pace; replay derives it from events only",
            )
        )
    else:
        live_pace = live.appliedPaceSecPer100M
        checks.append(
            _check(
                "state.live_replay_applied_pace",
                live_pace is not None and abs(live_pace - replay.appliedPaceSecPer100M) <= _TOL,
                expected=live_pace,
                actual=replay.appliedPaceSecPer100M,
            )
        )
    return checks


# --------------------------------------------------------------------------- clock invariants
def check_clock_invariants(
    replay: HistoricalSessionState, case: Phase1E2ECase
) -> list[Phase1VerificationCheck]:
    checks: list[Phase1VerificationCheck] = []
    durations = {
        "active": replay.activeDurationMs,
        "stopped": replay.stoppedDurationMs,
        "lifecycle_paused": replay.lifecyclePausedDurationMs,
        "elapsed": replay.elapsedDurationMs,
        "wall": replay.wallDurationMs,
    }
    checks.append(
        _check(
            "clock.durations_non_negative",
            all(value >= 0 for value in durations.values()),
            actual=durations,
        )
    )
    checks.append(
        _check(
            "clock.elapsed_equals_active_plus_stopped",
            replay.elapsedDurationMs == replay.activeDurationMs + replay.stoppedDurationMs,
            expected=replay.activeDurationMs + replay.stoppedDurationMs,
            actual=replay.elapsedDurationMs,
        )
    )
    checks.append(
        _check(
            "clock.wall_equals_elapsed_plus_lifecycle_pause",
            replay.wallDurationMs == replay.elapsedDurationMs + replay.lifecyclePausedDurationMs,
            expected=replay.elapsedDurationMs + replay.lifecyclePausedDurationMs,
            actual=replay.wallDurationMs,
        )
    )
    interval_total = sum(interval.durationMs or 0 for interval in replay.completedStopPauses)
    if replay.openStopPause is None:
        checks.append(
            _check(
                "clock.stopped_equals_interval_sum",
                interval_total == replay.stoppedDurationMs,
                expected=interval_total,
                actual=replay.stoppedDurationMs,
            )
        )
    else:
        checks.append(
            _skip("clock.stopped_equals_interval_sum", "an open StopPause is still running")
        )
    checks.append(
        _check(
            "clock.lifecycle_pause_is_a_separate_axis",
            replay.lifecyclePausedDurationMs == 0
            or replay.lifecyclePausedDurationMs == replay.wallDurationMs - replay.elapsedDurationMs,
            actual=replay.lifecyclePausedDurationMs,
        )
    )
    expected_stopped = case.expectedOutcome.stoppedDurationMs
    if expected_stopped is None:
        checks.append(
            _skip("clock.case_expected_stopped_duration", "the case pins no stopped duration")
        )
    else:
        checks.append(
            _check(
                "clock.case_expected_stopped_duration",
                replay.stoppedDurationMs == expected_stopped,
                expected=expected_stopped,
                actual=replay.stoppedDurationMs,
            )
        )
    # A pace loss or a coach curve reset must never create stopped time by itself.
    if case.expectedOutcome.stopPauseCount == 0:
        checks.append(
            _check(
                "clock.no_stop_without_stop_pause",
                replay.stoppedDurationMs == 0 and not replay.completedStopPauses,
                expected=0,
                actual=replay.stoppedDurationMs,
                message="pace loss / coach reset must not produce stopped duration",
            )
        )
    else:
        checks.append(
            _skip("clock.no_stop_without_stop_pause", "the case intentionally injects a StopPause")
        )
    return checks


# --------------------------------------------------------------------------- distance invariants
def check_distance_invariants(
    replay: HistoricalSessionState,
    workout: AnyWorkoutTemplate,
    report: SessionReportV1_1,
) -> list[Phase1VerificationCheck]:
    checks: list[Phase1VerificationCheck] = []
    planned = float(sum(block.repetitions * block.distanceM for block in workout.blocks))
    pool = replay.poolLengthM
    completed = replay.officialCompletedDistanceM
    checks.append(
        _check(
            "distance.pool_length_matches_workout",
            pool == workout.poolLengthM,
            expected=workout.poolLengthM,
            actual=pool,
        )
    )
    if pool is None or completed is None:
        checks.append(_skip("distance.geometry_multiple", "no official distance recorded"))
    else:
        checks.append(
            _check(
                "distance.geometry_multiple",
                abs(completed - replay.officialCompletedLengthCount * pool) <= _TOL,
                expected=replay.officialCompletedLengthCount * pool,
                actual=completed,
            )
        )
        checks.append(
            _check(
                "distance.never_exceeds_planned",
                completed <= planned + _TOL,
                expected=f"<= {planned}",
                actual=completed,
            )
        )
    length_indices = [split.lengthIndex for split in replay.recordedSplits]
    checks.append(
        _check(
            "distance.no_duplicate_length_index",
            len(set(length_indices)) == len(length_indices),
            expected=len(length_indices),
            actual=len(set(length_indices)),
        )
    )
    checks.append(
        _check(
            "distance.length_indices_sequential",
            length_indices == sorted(length_indices),
            actual=length_indices,
        )
    )
    official_splits_on_walls = all(
        pool is not None
        and split.officialDistanceM is not None
        and abs(split.officialDistanceM - (split.lengthIndex + 1) * pool) <= _TOL
        for split in replay.recordedSplits
    )
    checks.append(
        _check(
            "distance.official_splits_land_on_walls",
            official_splits_on_walls or not replay.recordedSplits,
            message="official split distance comes from pool geometry, never an estimate",
        )
    )
    report_distance = report.distanceSummary.officialCompletedDistanceM
    checks.append(
        _check(
            "distance.report_matches_replay",
            (report_distance is None and completed is None)
            or (
                report_distance is not None
                and completed is not None
                and abs(report_distance - completed) <= _TOL
            ),
            expected=completed,
            actual=report_distance,
        )
    )
    curve = report.continuousCurveAnalysis
    if curve.available and completed is not None:
        # An estimated/observed position may never become official distance.
        checks.append(
            _check(
                "distance.estimate_is_not_official",
                abs((report.distanceSummary.officialCompletedDistanceM or 0.0) - completed) <= _TOL,
                message="continuous observations are analytical only",
            )
        )
    else:
        checks.append(
            _skip("distance.estimate_is_not_official", "no trusted continuous curve was built")
        )
    return checks


# --------------------------------------------------------------------------- profile invariants
def check_profile_invariants(
    case: Phase1E2ECase,
    replay: HistoricalSessionState,
    timeline: PaceTimeline,
    workout: AnyWorkoutTemplate,
) -> list[Phase1VerificationCheck]:
    checks: list[Phase1VerificationCheck] = []
    initial = case.profile_by_id(case.selectedProfileId)
    checks.append(
        _check(
            "profile.pool_matches_workout",
            initial.poolLengthM == workout.poolLengthM,
            expected=workout.poolLengthM,
            actual=initial.poolLengthM,
        )
    )
    checks.append(
        _check(
            "profile.stroke_matches_workout",
            initial.stroke == workout.stroke,
            expected=workout.stroke.value,
            actual=initial.stroke.value,
        )
    )
    if isinstance(workout, WorkoutTemplateV1_1):
        resolved = resolve_repeat_start_mode(workout, 0, 0)
        checks.append(
            _check(
                "profile.start_mode_matches_workout",
                initial.startMode.value == resolved.value,
                expected=resolved.value,
                actual=initial.startMode.value,
            )
        )
    else:
        checks.append(
            _skip("profile.start_mode_matches_workout", "workout 1.0 carries no start policy")
        )
    planned = float(sum(block.repetitions * block.distanceM for block in workout.blocks))
    checks.append(
        _check(
            "profile.distance_matches_workout",
            abs(float(initial.totalDistanceM) - planned) <= _TOL,
            expected=planned,
            actual=initial.totalDistanceM,
        )
    )
    target_total = _profile_total_time(initial)
    checks.append(
        _check(
            "profile.timeline_reconciles_to_target_total",
            abs(timeline.totalActiveDurationSec - target_total) <= 1e-5,
            expected=target_total,
            actual=timeline.totalActiveDurationSec,
        )
    )
    checks.append(
        _check(
            "profile.timeline_covers_full_distance",
            abs(timeline.totalDistanceM - planned) <= _TOL,
            expected=planned,
            actual=timeline.totalDistanceM,
        )
    )
    if isinstance(initial, ApprovedContinuousPaceProfile) and initial.splitTimeConstraints:
        locked_ok = True
        for constraint in initial.splitTimeConstraints:
            if not constraint.lockedByCoach:
                continue
            span = [
                interval
                for interval in timeline.intervals
                if interval.fromM >= constraint.fromM - _TOL
                and interval.toM <= constraint.toM + _TOL
            ]
            achieved = sum(interval.activeDurationSec for interval in span)
            if abs(achieved - constraint.targetDurationSec) > 1e-5:
                locked_ok = False
        checks.append(
            _check(
                "profile.locked_splits_preserved",
                locked_ok,
                message="locked split durations are hard constraints",
            )
        )
    else:
        checks.append(_skip("profile.locked_splits_preserved", "no locked split constraints"))

    expected_final = case.expectedOutcome.finalProfileId or case.selectedProfileId
    checks.append(
        _check(
            "profile.final_selection_authority",
            replay.selectedPaceProfileId == expected_final,
            expected=expected_final,
            actual=replay.selectedPaceProfileId,
        )
    )
    expected_source = case.expectedOutcome.finalProfileSource
    if expected_source is None:
        checks.append(_skip("profile.final_source", "the case pins no final profile source"))
    else:
        checks.append(
            _check(
                "profile.final_source",
                replay.selectedPaceProfileSource == expected_source,
                expected=expected_source,
                actual=replay.selectedPaceProfileSource,
            )
        )
    expected_lock = case.expectedOutcome.finalProfileCoachLocked
    if expected_lock is None:
        checks.append(_skip("profile.coach_lock_preserved", "the case pins no coach lock"))
    else:
        checks.append(
            _check(
                "profile.coach_lock_preserved",
                replay.profileCoachLocked == expected_lock,
                expected=expected_lock,
                actual=replay.profileCoachLocked,
            )
        )
    return checks


# --------------------------------------------------------------------------- report invariants
def check_report_invariants(
    report: SessionReportV1_1,
    report_bytes: bytes,
    events: Sequence[EventEnvelope],
    replay: HistoricalSessionState,
) -> list[Phase1VerificationCheck]:
    checks: list[Phase1VerificationCheck] = []
    checks.append(
        _check(
            "report.session_id_matches_events",
            report.sessionId == events[0].sessionId,
            expected=events[0].sessionId,
            actual=report.sessionId,
        )
    )
    checks.append(
        _check(
            "report.last_seq_matches_journal",
            report.createdFromLastSeq == events[-1].seq == replay.lastSeq,
            expected=events[-1].seq,
            actual=report.createdFromLastSeq,
        )
    )
    digest = event_digest_sha256(events)
    checks.append(
        _check(
            "report.event_digest_matches",
            report.provenance.eventDigestSha256 == digest,
            expected=digest,
            actual=report.provenance.eventDigestSha256,
        )
    )
    expected_id = deterministic_report_id(report)
    checks.append(
        _check(
            "report.content_addressed_id",
            report.reportId == expected_id,
            expected=expected_id,
            actual=report.reportId,
        )
    )
    checks.append(
        _check(
            "report.canonical_bytes",
            encode_session_report(report) == report_bytes,
            message="stored report bytes must be the canonical encoding",
        )
    )
    checks.append(
        _check(
            "report.generated_at_is_event_derived",
            report.reportGeneratedAtMs == replay.lastEventTimestampMs,
            expected=replay.lastEventTimestampMs,
            actual=report.reportGeneratedAtMs,
        )
    )
    provenance_pairs = [
        ("profile_id", report.provenance.paceProfileId, replay.selectedPaceProfileId),
        (
            "profile_version",
            report.provenance.paceProfileVersion,
            replay.selectedPaceProfileVersion,
        ),
        ("profile_source", report.provenance.paceProfileSource, replay.selectedPaceProfileSource),
        ("profile_type", report.provenance.paceProfileType, replay.selectedPaceProfileType),
        (
            "curve_representation",
            report.provenance.curveRepresentation,
            replay.selectedCurveRepresentation,
        ),
    ]
    for name, report_value, replay_value in provenance_pairs:
        checks.append(
            _check(
                f"report.provenance_matches_replay_{name}",
                report_value == replay_value,
                expected=replay_value,
                actual=report_value,
            )
        )
    context = report.paceProfileContext
    forecast_fields = (
        context.predictedSplitTimesSec,
        context.predictedNextSplitTimeSec,
        context.predictedNextRepeatTimeSec,
    )
    checks.append(
        _check(
            "report.target_and_forecast_separated",
            all(value is None for value in forecast_fields)
            or context.targetTotalTimeSec is not None,
            message="a forecast never replaces the coach target",
        )
    )
    fabricated: list[str] = []
    aggregate = report.splitAnalysis.aggregate
    if aggregate.eligibleSplitCount == 0:
        for name, value in (
            ("meanAbsoluteSplitErrorSec", aggregate.meanAbsoluteSplitErrorSec),
            ("rootMeanSquaredSplitErrorSec", aggregate.rootMeanSquaredSplitErrorSec),
            ("targetPaceAdherenceRatio", aggregate.targetPaceAdherenceRatio),
        ):
            if value is not None:
                fabricated.append(name)
    curve = report.continuousCurveAnalysis
    if not curve.available:
        for name, value in (
            ("curveDeviationMean", curve.curveDeviationMean),
            ("curveDeviationRms", curve.curveDeviationRms),
            ("peakPositiveDeviation", curve.peakPositiveDeviation),
        ):
            if value is not None:
                fabricated.append(name)
    if (
        not report.sensorAnalysis.heartRate.available
        and report.sensorAnalysis.heartRate.averageHeartRateBpm is not None
    ):
        fabricated.append("averageHeartRateBpm")
    checks.append(
        _check(
            "report.missing_data_is_not_fabricated",
            not fabricated,
            actual=fabricated,
            message="unavailable metrics stay None, never synthetic zero",
        )
    )
    finite_ok = True
    for split in report.splitAnalysis.splits:
        for value in (split.actualDurationSec, split.actualSpeedMps, split.durationDeltaSec):
            if value is not None and not math.isfinite(value):
                finite_ok = False
    checks.append(_check("report.numeric_fields_finite", finite_ok))
    checks.append(
        _check(
            "report.synthetic_provenance_marked",
            report.provenance.simulatorSynthetic is True,
            expected=True,
            actual=report.provenance.simulatorSynthetic,
            message="simulator-produced reports are never real performance evidence",
        )
    )
    return checks


# --------------------------------------------------------------------------- expected outcome
def check_expected_outcome(
    case: Phase1E2ECase,
    replay: HistoricalSessionState,
    report: SessionReportV1_1,
    outcomes: Sequence[CommandOutcome],
    profiles: Sequence[ApprovedPaceProfileVersion],
) -> list[Phase1VerificationCheck]:
    expected = case.expectedOutcome
    checks: list[Phase1VerificationCheck] = [
        _check(
            "case.lifecycle_state",
            replay.lifecycleState.value == expected.lifecycleState,
            expected=expected.lifecycleState,
            actual=replay.lifecycleState.value,
        )
    ]
    if expected.officialDistanceM is not None:
        checks.append(
            _check(
                "case.official_distance",
                replay.officialCompletedDistanceM is not None
                and abs(replay.officialCompletedDistanceM - expected.officialDistanceM) <= _TOL,
                expected=expected.officialDistanceM,
                actual=replay.officialCompletedDistanceM,
            )
        )
    if expected.poolLengthM is not None:
        checks.append(
            _check(
                "case.pool_length",
                replay.poolLengthM == expected.poolLengthM,
                expected=expected.poolLengthM,
                actual=replay.poolLengthM,
            )
        )
    if expected.officialLengthCount is not None:
        checks.append(
            _check(
                "case.official_length_count",
                replay.officialCompletedLengthCount == expected.officialLengthCount,
                expected=expected.officialLengthCount,
                actual=replay.officialCompletedLengthCount,
            )
        )
    stop_count = len(replay.completedStopPauses) + (1 if replay.openStopPause else 0)
    checks.append(
        _check(
            "case.stop_pause_count",
            stop_count == expected.stopPauseCount,
            expected=expected.stopPauseCount,
            actual=stop_count,
        )
    )
    checks.append(
        _check(
            "case.report_stop_pause_count",
            report.stopPauseAnalysis.stopPauseCount == expected.stopPauseCount,
            expected=expected.stopPauseCount,
            actual=report.stopPauseAnalysis.stopPauseCount,
        )
    )
    checks.append(
        _check(
            "case.coach_reset_applied_count",
            report.coachResetAnalysis.coachResetAppliedCount == expected.coachResetAppliedCount,
            expected=expected.coachResetAppliedCount,
            actual=report.coachResetAnalysis.coachResetAppliedCount,
        )
    )
    rejected = sum(1 for outcome in outcomes if outcome.outcome == "REJECTED")
    checks.append(
        _check(
            "case.rejected_command_count",
            rejected == expected.rejectedCommandCount,
            expected=expected.rejectedCommandCount,
            actual=rejected,
        )
    )
    replays = sum(1 for outcome in outcomes if outcome.outcome == "IDEMPOTENT_REPLAY")
    checks.append(
        _check(
            "case.idempotent_replay_count",
            replays == expected.idempotentReplayCount,
            expected=expected.idempotentReplayCount,
            actual=replays,
        )
    )
    rejected_produced_events = any(
        outcome.outcome == "REJECTED" and outcome.eventCount != 0 for outcome in outcomes
    )
    checks.append(
        _check(
            "case.rejected_commands_produced_no_events",
            not rejected_produced_events,
            message="a failed command never appends to the journal",
        )
    )
    if expected.continuousCurveAvailable is None:
        checks.append(_skip("case.continuous_curve_availability", "the case pins no expectation"))
    else:
        checks.append(
            _check(
                "case.continuous_curve_availability",
                report.continuousCurveAnalysis.available == expected.continuousCurveAvailable,
                expected=expected.continuousCurveAvailable,
                actual=report.continuousCurveAnalysis.available,
            )
        )
    if expected.datasetEvidenceAssetIds is None:
        checks.append(_skip("case.dataset_evidence_ids", "the case pins no dataset evidence"))
    else:
        checks.append(
            _check(
                "case.dataset_evidence_ids",
                tuple(report.provenance.datasetEvidenceAssetIds)
                == expected.datasetEvidenceAssetIds,
                expected=expected.datasetEvidenceAssetIds,
                actual=report.provenance.datasetEvidenceAssetIds,
            )
        )
    if expected.curveEvidenceLevel is None:
        checks.append(_skip("case.curve_evidence_level", "the case pins no evidence level"))
    else:
        checks.append(
            _check(
                "case.curve_evidence_level",
                report.provenance.curveEvidenceLevel == expected.curveEvidenceLevel,
                expected=expected.curveEvidenceLevel,
                actual=report.provenance.curveEvidenceLevel,
            )
        )
    if expected.requireNotGroundTruth:
        ground_truth_claims = [
            profile.profileId
            for profile in profiles
            if isinstance(profile, ApprovedContinuousPaceProfile)
            and profile.curveProvenance.continuousCurveGroundTruth
        ]
        checks.append(
            _check(
                "case.not_measured_velocity_ground_truth",
                not ground_truth_claims
                and report.provenance.continuousCurveGroundTruth is not True,
                actual=ground_truth_claims,
                message="a coarse-split-derived envelope is not measured velocity",
            )
        )
    else:
        checks.append(
            _skip("case.not_measured_velocity_ground_truth", "the case pins no evidence claim")
        )
    return checks


def _drop_representation_metadata(value: object) -> object:
    """Normalize only schema/curve representation details for migration comparisons."""
    ignored = {
        "paceProfileSchemaVersion",
        "profileSchemaVersion",
        "curveRepresentation",
        "curveCompilerVersion",
        "selectedCurveRepresentation",
        "selectedCurveCompilerVersion",
    }
    if isinstance(value, dict):
        return {
            key: _drop_representation_metadata(item)
            for key, item in value.items()
            if key not in ignored
        }
    if isinstance(value, list | tuple):
        return [_drop_representation_metadata(item) for item in value]
    return value


def _migration_report_number(value: float | None) -> float | None:
    """Remove sub-nanosecond float noise without hiding meaningful differences."""
    if value is None:
        return None
    return round(value, 9)


def _report_equivalence_projection(report: SessionReportV1_1) -> dict[str, object]:
    return {
        "sessionId": report.sessionId,
        "createdFromLastSeq": report.createdFromLastSeq,
        "timingSummary": report.timingSummary.model_dump(mode="json", exclude_none=False),
        "distanceSummary": report.distanceSummary.model_dump(mode="json", exclude_none=False),
        "splits": [
            {
                "splitIndex": item.splitIndex,
                "fromM": item.fromM,
                "toM": item.toM,
                "targetDurationSec": _migration_report_number(item.targetDurationSec),
                "actualDurationSec": _migration_report_number(item.actualDurationSec),
                "durationDeltaSec": _migration_report_number(item.durationDeltaSec),
                "aheadBehindStatus": item.aheadBehindStatus.value,
                "targetStatus": item.targetStatus.value,
            }
            for item in report.splitAnalysis.splits
        ],
    }


def check_migration_equivalence(
    case: Phase1E2ECase,
    timeline: PaceTimeline,
    report: SessionReportV1_1,
    *,
    primary_simulation: SimulationResult,
    partner_simulation: SimulationResult | None,
    partner_report: SessionReportV1_1 | None,
) -> list[Phase1VerificationCheck]:
    """Prove legacy/migrated equivalence through two complete runtime chains."""
    partner = case.equivalenceProfile
    if partner is None:
        return [
            _skip(
                "migration.full_session_equivalence",
                "the case declares no equivalence partner",
            )
        ]
    if partner_simulation is None or partner_report is None:
        return [
            _check(
                "migration.full_session_equivalence",
                False,
                message="the equivalence partner was not executed through the real runtime",
            )
        ]

    partner_timeline = compile_ghost_timeline(partner, case.workout)
    checks: list[Phase1VerificationCheck] = [
        _check(
            "migration.total_duration_equivalent",
            abs(partner_timeline.totalActiveDurationSec - timeline.totalActiveDurationSec) <= 1e-9,
            expected=timeline.totalActiveDurationSec,
            actual=partner_timeline.totalActiveDurationSec,
            message="the migration must not change the approved total time",
        ),
        _check(
            "migration.total_distance_equivalent",
            abs(partner_timeline.totalDistanceM - timeline.totalDistanceM) <= _TOL,
            expected=timeline.totalDistanceM,
            actual=partner_timeline.totalDistanceM,
        ),
        _check(
            "migration.interval_coverage_equivalent",
            abs(timeline.intervals[0].fromM - partner_timeline.intervals[0].fromM) <= _TOL
            and abs(timeline.intervals[-1].toM - partner_timeline.intervals[-1].toM) <= _TOL,
            message="both representations must cover exactly the same distance span",
        ),
    ]

    def worst_target_difference(distances: Sequence[float]) -> tuple[float, float]:
        worst = 0.0
        at_distance = 0.0
        for distance in distances:
            left = target_active_time_at_distance(timeline, distance).elapsedActiveSec
            right = target_active_time_at_distance(partner_timeline, distance).elapsedActiveSec
            difference = abs(left - right)
            if difference > worst:
                worst, at_distance = difference, distance
        return worst, at_distance

    total_distance = timeline.totalDistanceM
    samples = [
        min(index * _MIGRATION_SAMPLE_STEP_M, total_distance)
        for index in range(int(total_distance / _MIGRATION_SAMPLE_STEP_M) + 1)
    ]
    sampled_worst, sampled_at = worst_target_difference(samples)
    checks.append(
        _check(
            "migration.target_function_equivalent",
            sampled_worst <= MIGRATION_TARGET_TOLERANCE_SEC,
            expected=f"<= {MIGRATION_TARGET_TOLERANCE_SEC} s over {len(samples)} samples",
            actual=f"{sampled_worst} s at {sampled_at} m",
        )
    )

    pool = case.workout.poolLengthM
    wall_count = int(round(total_distance / pool))
    wall_distances = [
        min(float(index * pool), total_distance) for index in range(1, wall_count + 1)
    ]
    wall_worst, wall_at = worst_target_difference(wall_distances)
    checks.append(
        _check(
            "migration.target_wall_times_equivalent",
            wall_worst <= MIGRATION_TARGET_TOLERANCE_SEC,
            expected=f"<= {MIGRATION_TARGET_TOLERANCE_SEC} s over {wall_count} walls",
            actual=f"{wall_worst} s at {wall_at} m",
        )
    )

    primary_outcomes = [asdict(item) for item in primary_simulation.commandOutcomes]
    partner_outcomes = [asdict(item) for item in partner_simulation.commandOutcomes]
    checks.append(
        _check(
            "migration.command_outcomes_equivalent",
            primary_outcomes == partner_outcomes,
            message="both representations must drive the same accepted/rejected commands",
        )
    )

    primary_events = _drop_representation_metadata(
        [event.model_dump(mode="json", exclude_none=False) for event in primary_simulation.events]
    )
    partner_events = _drop_representation_metadata(
        [event.model_dump(mode="json", exclude_none=False) for event in partner_simulation.events]
    )
    checks.append(
        _check(
            "migration.journal_semantics_equivalent",
            primary_events == partner_events,
            message=(
                "the second real journal may differ only in representation-specific "
                "schema/curve metadata"
            ),
        )
    )
    primary_batch_shape = [
        [event.seq for event in batch] for batch in primary_simulation.eventBatches
    ]
    partner_batch_shape = [
        [event.seq for event in batch] for batch in partner_simulation.eventBatches
    ]
    checks.append(
        _check(
            "migration.journal_batch_structure_equivalent",
            primary_batch_shape == partner_batch_shape,
            message="both journals must group the same event sequence into command batches",
        )
    )

    primary_live = _drop_representation_metadata(asdict(primary_simulation.liveFinalState))
    partner_live = _drop_representation_metadata(asdict(partner_simulation.liveFinalState))
    checks.append(
        _check(
            "migration.live_session_output_equivalent",
            primary_live == partner_live,
            message="both real aggregates must finish in the same semantic state",
        )
    )

    primary_replay = _drop_representation_metadata(asdict(primary_simulation.replayResult.state))
    partner_replay = _drop_representation_metadata(asdict(partner_simulation.replayResult.state))
    checks.append(
        _check(
            "migration.replay_state_equivalent",
            primary_replay == partner_replay,
            message="both persisted journals must replay to the same semantic state",
        )
    )

    checks.append(
        _check(
            "migration.report_output_equivalent",
            _report_equivalence_projection(report)
            == _report_equivalence_projection(partner_report),
            message="report timing, distance and split outputs must be equivalent",
        )
    )

    worst_split = 0.0
    worst_split_index: int | None = None
    for split in report.splitAnalysis.splits:
        if split.targetDurationSec is None:
            continue
        start = target_active_time_at_distance(partner_timeline, split.fromM).elapsedActiveSec
        end = target_active_time_at_distance(partner_timeline, split.toM).elapsedActiveSec
        difference = abs((end - start) - split.targetDurationSec)
        if difference > worst_split:
            worst_split, worst_split_index = difference, split.splitIndex
    checks.append(
        _check(
            "migration.report_split_targets_equivalent",
            worst_split <= MIGRATION_TARGET_TOLERANCE_SEC,
            expected=f"<= {MIGRATION_TARGET_TOLERANCE_SEC} s",
            actual=f"{worst_split} s at split {worst_split_index}",
        )
    )
    return checks


__all__ = [
    "MIGRATION_TARGET_TOLERANCE_SEC",
    "check_clock_invariants",
    "check_distance_invariants",
    "check_event_invariants",
    "check_expected_outcome",
    "check_migration_equivalence",
    "check_profile_invariants",
    "check_report_invariants",
    "check_state_invariants",
]
