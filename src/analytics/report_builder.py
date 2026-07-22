"""Pure orchestration for deterministic SessionReport 1.1 construction."""

from __future__ import annotations

from collections.abc import Sequence

from analytics.confidence import build_report_data_quality
from analytics.curves import build_continuous_curve_analysis
from analytics.errors import ReplayStateMismatchError, ReportInputError
from analytics.identity import (
    canonical_digest_sha256,
    deterministic_report_id,
    event_digest_sha256,
)
from analytics.pacing import build_coach_reset_analysis, build_pacing_analysis
from analytics.sensors import build_sensor_analysis
from analytics.splits import build_split_analysis
from analytics.stops import build_stop_pause_analysis
from analytics.types import (
    ApprovedPaceProfileVersion,
    ReportBuildContext,
    SensorObservation,
    SessionObservation,
)
from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.enums import EventType
from contracts.events import (
    CoachPacingResetAppliedPayload,
    EventEnvelope,
    SessionCreatedPayload,
)
from contracts.session_report import (
    DistanceSummary,
    MetricStatus,
    PaceProfileContextV1_1,
    ReportCompletionStatus,
    ReportProvenance,
    SessionReportV1_1,
    SessionSummary,
    TimingSummary,
)
from contracts.workout import AnyWorkoutTemplate, WorkoutTemplateV1_1
from swimcore.pacing.types import PaceTimeline
from swimcore.replay.reducer import replay_session
from swimcore.replay.state import HistoricalSessionState
from swimcore.workout.start_mode import resolve_repeat_start_mode


def _analytics_policy_material(context: ReportBuildContext) -> dict[str, object]:
    return {
        "analyticsVersion": context.analyticsVersion,
        "reportBuilderVersion": context.reportBuilderVersion,
        "reportSchemaVersion": context.reportSchemaVersion,
        "reportVersion": context.reportVersion,
        "adherenceToleranceSec": context.adherenceToleranceSec,
        "onTargetTolerancePct": context.onTargetTolerancePct,
        "curveAdherenceToleranceM": context.curveAdherenceToleranceM,
        "minimumTrustedCurveObservations": context.minimumTrustedCurveObservations,
        "minimumCurveCoverageRatio": context.minimumCurveCoverageRatio,
        "maximumLowQualityObservationRatio": context.maximumLowQualityObservationRatio,
        "minimumConsecutiveDecliningSplits": context.minimumConsecutiveDecliningSplits,
        "minimumDeclinePct": context.minimumDeclinePct,
        "unexpectedCollapseMarginPct": context.unexpectedCollapseMarginPct,
        "minimumPacingShapeSplits": context.minimumPacingShapeSplits,
        "minimumSensorSamplesForTrend": context.minimumSensorSamplesForTrend,
        "simulatorSynthetic": context.simulatorSynthetic,
        "simulationRunId": context.simulationRunId,
    }


def _planned_distance(workout: AnyWorkoutTemplate) -> float:
    return float(sum(block.repetitions * block.distanceM for block in workout.blocks))


def _completion_status(state: HistoricalSessionState) -> ReportCompletionStatus:
    value = state.lifecycleState.value
    if value == "COMPLETED":
        return ReportCompletionStatus.COMPLETED
    if value == "ABORTED":
        return ReportCompletionStatus.ABORTED
    if state.startedAtMs is None:
        return ReportCompletionStatus.NOT_STARTED
    return ReportCompletionStatus.IN_PROGRESS


def _final_profile(
    state: HistoricalSessionState,
    supplied: ApprovedPaceProfileVersion | None,
    context: ReportBuildContext,
) -> ApprovedPaceProfileVersion | None:
    if state.selectedPaceProfileId is not None and state.selectedPaceProfileVersion is not None:
        runtime = context.profileRegistry.get(
            (state.selectedPaceProfileId, state.selectedPaceProfileVersion)
        )
        if runtime is not None:
            return runtime.profile
    if (
        supplied is not None
        and supplied.profileId == state.selectedPaceProfileId
        and supplied.profileVersion == state.selectedPaceProfileVersion
    ):
        return supplied
    return None


def _profile_target_total_time(profile: ApprovedPaceProfileVersion) -> float:
    if isinstance(profile, ApprovedContinuousPaceProfile):
        return profile.targetTimeConstraint.targetTotalTimeSec
    return profile.targetTotalTimeSec


def _resolved_workout_start_mode(workout: AnyWorkoutTemplate) -> str | None:
    if isinstance(workout, WorkoutTemplateV1_1):
        return resolve_repeat_start_mode(workout, 0, 0).value
    return None


def _validate_profile_runtime(
    *,
    label: str,
    workout: AnyWorkoutTemplate,
    profile: ApprovedPaceProfileVersion,
    timeline: PaceTimeline,
    planned_distance: float,
) -> None:
    if profile.poolLengthM != workout.poolLengthM:
        raise ReportInputError(
            f"{label} profile pool {profile.poolLengthM} != workout pool {workout.poolLengthM}"
        )
    if profile.stroke != workout.stroke:
        raise ReportInputError(
            f"{label} profile stroke {profile.stroke.value} != "
            f"workout stroke {workout.stroke.value}"
        )
    resolved_start = _resolved_workout_start_mode(workout)
    if resolved_start is not None and profile.startMode.value != resolved_start:
        raise ReportInputError(
            f"{label} profile start mode {profile.startMode.value} != workout start mode "
            f"{resolved_start}"
        )
    if isinstance(workout, WorkoutTemplateV1_1) and profile.workoutGoal != workout.workoutGoal:
        raise ReportInputError(
            f"{label} profile workout goal {profile.workoutGoal.value} != workout goal "
            f"{workout.workoutGoal.value}"
        )
    if abs(float(profile.totalDistanceM) - planned_distance) > 1e-6:
        raise ReportInputError(
            f"{label} profile distance {profile.totalDistanceM} != workout distance "
            f"{planned_distance}"
        )
    if abs(timeline.totalDistanceM - planned_distance) > 1e-6:
        raise ReportInputError(
            f"{label} timeline distance {timeline.totalDistanceM} != workout distance "
            f"{planned_distance}"
        )
    target_total = _profile_target_total_time(profile)
    if abs(timeline.totalActiveDurationSec - target_total) > 1e-5:
        raise ReportInputError(
            f"{label} timeline duration {timeline.totalActiveDurationSec} != profile target "
            f"{target_total}"
        )
    if not timeline.intervals:
        raise ReportInputError(f"{label} timeline has no intervals")
    if abs(timeline.intervals[0].fromM) > 1e-6:
        raise ReportInputError(f"{label} timeline must start at 0 m")
    if abs(timeline.intervals[-1].toM - planned_distance) > 1e-6:
        raise ReportInputError(
            f"{label} timeline interval coverage ends at {timeline.intervals[-1].toM}, "
            f"expected {planned_distance}"
        )
    previous_to = 0.0
    interval_duration = 0.0
    for interval in timeline.intervals:
        if interval.toM <= interval.fromM:
            raise ReportInputError(f"{label} timeline contains a non-positive interval")
        if abs(interval.fromM - previous_to) > 1e-6:
            raise ReportInputError(f"{label} timeline contains a gap or overlap")
        previous_to = interval.toM
        interval_duration += interval.activeDurationSec
        if interval.profileId is not None and interval.profileId != profile.profileId:
            raise ReportInputError(
                f"{label} timeline profile id {interval.profileId} != {profile.profileId}"
            )
        if interval.profileSource is not None and interval.profileSource != profile.source.value:
            raise ReportInputError(
                f"{label} timeline profile source {interval.profileSource} != "
                f"{profile.source.value}"
            )
        if interval.profileType is not None and interval.profileType != profile.profileType.value:
            raise ReportInputError(
                f"{label} timeline profile type {interval.profileType} != "
                f"{profile.profileType.value}"
            )
        if interval.startMode is not None and interval.startMode != profile.startMode.value:
            raise ReportInputError(
                f"{label} timeline start mode {interval.startMode} != {profile.startMode.value}"
            )
        if (
            interval.curveProfileVersion is not None
            and interval.curveProfileVersion != profile.profileVersion
        ):
            raise ReportInputError(
                f"{label} timeline profile version {interval.curveProfileVersion} != "
                f"{profile.profileVersion}"
            )
    if abs(interval_duration - timeline.totalActiveDurationSec) > 1e-5:
        raise ReportInputError(
            f"{label} timeline interval durations sum to {interval_duration}, not "
            f"{timeline.totalActiveDurationSec}"
        )


def _validate_report_inputs(
    *,
    replay_state: HistoricalSessionState,
    events: Sequence[EventEnvelope],
    workout: AnyWorkoutTemplate,
    pace_profile: ApprovedPaceProfileVersion | None,
    compiled_timeline: PaceTimeline | None,
    report_context: ReportBuildContext,
    planned_distance: float,
) -> None:
    if workout.poolLengthM != replay_state.poolLengthM:
        raise ReportInputError(
            f"workout pool {workout.poolLengthM} != replay pool {replay_state.poolLengthM}"
        )
    created_payload: SessionCreatedPayload | None = None
    replacements: list[CoachPacingResetAppliedPayload] = []
    for event in events:
        if event.type is EventType.SessionCreated:
            payload = event.payload
            assert isinstance(payload, SessionCreatedPayload)
            created_payload = payload
        elif event.type is EventType.CoachPacingResetApplied:
            payload = event.payload
            assert isinstance(payload, CoachPacingResetAppliedPayload)
            if payload.replacementPaceProfileId is not None:
                replacements.append(payload)
    if created_payload is None:
        raise ReportInputError("event stream has no SessionCreated payload")

    if pace_profile is None:
        if compiled_timeline is not None:
            raise ReportInputError("compiled timeline supplied without an initial pace profile")
    else:
        if compiled_timeline is None:
            raise ReportInputError("pace profile requires its compiled timeline")
        if (
            created_payload.selectedPaceProfileId is not None
            and pace_profile.profileId != created_payload.selectedPaceProfileId
        ):
            raise ReportInputError(
                f"initial profile id {pace_profile.profileId} != replay-selected initial id "
                f"{created_payload.selectedPaceProfileId}"
            )
        if (
            created_payload.selectedPaceProfileVersion is not None
            and pace_profile.profileVersion != created_payload.selectedPaceProfileVersion
        ):
            raise ReportInputError(
                f"initial profile version {pace_profile.profileVersion} != replay-selected "
                f"initial version {created_payload.selectedPaceProfileVersion}"
            )
        if (
            created_payload.selectedPaceProfileSource is not None
            and pace_profile.source.value != created_payload.selectedPaceProfileSource
        ):
            raise ReportInputError("initial profile source conflicts with SessionCreated")
        if (
            created_payload.selectedPaceProfileType is not None
            and pace_profile.profileType.value != created_payload.selectedPaceProfileType
        ):
            raise ReportInputError("initial profile type conflicts with SessionCreated")
        if pace_profile.coachLocked != created_payload.profileCoachLocked:
            raise ReportInputError("initial profile coach-lock conflicts with SessionCreated")
        _validate_profile_runtime(
            label="initial",
            workout=workout,
            profile=pace_profile,
            timeline=compiled_timeline,
            planned_distance=planned_distance,
        )
        if (
            created_payload.selectedProfileTargetTotalTimeSec is not None
            and abs(
                _profile_target_total_time(pace_profile)
                - created_payload.selectedProfileTargetTotalTimeSec
            )
            > 1e-5
        ):
            raise ReportInputError("initial profile target total conflicts with SessionCreated")

    for key, runtime in report_context.profileRegistry.items():
        expected = (runtime.profile.profileId, runtime.profile.profileVersion)
        if key != expected:
            raise ReportInputError(f"profile registry key {key!r} != profile identity {expected!r}")
        _validate_profile_runtime(
            label=f"registry {key[0]}:{key[1]}",
            workout=workout,
            profile=runtime.profile,
            timeline=runtime.timeline,
            planned_distance=planned_distance,
        )

    for payload in replacements:
        key = (payload.replacementPaceProfileId or "", payload.replacementPaceProfileVersion or "")
        replacement_runtime = report_context.profileRegistry.get(key)
        if replacement_runtime is None:
            if pace_profile is not None:
                raise ReportInputError(
                    "replacement profile registry is missing applied coach-reset profile "
                    f"{key[0]}:{key[1]}"
                )
            continue
        if payload.replacementPaceProfileSource not in {
            None,
            replacement_runtime.profile.source.value,
        }:
            raise ReportInputError("replacement profile source conflicts with reset event")
        if payload.replacementPaceProfileType not in {
            None,
            replacement_runtime.profile.profileType.value,
        }:
            raise ReportInputError("replacement profile type conflicts with reset event")
        if payload.replacementProfileCoachLocked not in {
            None,
            replacement_runtime.profile.coachLocked,
        }:
            raise ReportInputError("replacement coach-lock conflicts with reset event")
        if (
            payload.replacementTargetTotalTimeSec is not None
            and abs(
                payload.replacementTargetTotalTimeSec
                - _profile_target_total_time(replacement_runtime.profile)
            )
            > 1e-5
        ):
            raise ReportInputError("replacement target total conflicts with reset event")
        if isinstance(replacement_runtime.profile, ApprovedContinuousPaceProfile):
            if payload.replacementCurveRepresentation not in {
                None,
                replacement_runtime.profile.curve.representation.value,
            }:
                raise ReportInputError(
                    "replacement curve representation conflicts with reset event"
                )
            compiler_version = (
                replacement_runtime.profile.curveValidationSummary.compilerVersion
                if replacement_runtime.profile.curveValidationSummary is not None
                else None
            )
            if compiler_version is not None and payload.replacementCurveCompilerVersion not in {
                None,
                compiler_version,
            }:
                raise ReportInputError(
                    "replacement curve compiler version conflicts with reset event"
                )

    final_profile = _final_profile(replay_state, pace_profile, report_context)
    if replay_state.selectedPaceProfileId is None:
        if final_profile is not None:
            raise ReportInputError("report inputs contain a profile but replay state has none")
    elif final_profile is None and pace_profile is not None:
        raise ReportInputError(
            "final replay-selected profile is unavailable; supply it through profileRegistry"
        )
    elif final_profile is not None and (
        final_profile.profileId != replay_state.selectedPaceProfileId
        or final_profile.profileVersion != replay_state.selectedPaceProfileVersion
    ):
        raise ReportInputError(
            "final replay-selected profile identity conflicts with report inputs"
        )
    elif final_profile is not None:
        if (
            replay_state.selectedPaceProfileSource is not None
            and final_profile.source.value != replay_state.selectedPaceProfileSource
        ):
            raise ReportInputError("final profile source conflicts with replay state")
        if (
            replay_state.selectedPaceProfileType is not None
            and final_profile.profileType.value != replay_state.selectedPaceProfileType
        ):
            raise ReportInputError("final profile type conflicts with replay state")
        if final_profile.coachLocked != replay_state.profileCoachLocked:
            raise ReportInputError("final profile coach-lock conflicts with replay state")
        if (
            replay_state.selectedProfileTargetTotalTimeSec is not None
            and abs(
                _profile_target_total_time(final_profile)
                - replay_state.selectedProfileTargetTotalTimeSec
            )
            > 1e-5
        ):
            raise ReportInputError("final profile target total conflicts with replay state")
        if isinstance(final_profile, ApprovedContinuousPaceProfile):
            if (
                replay_state.selectedCurveRepresentation is not None
                and final_profile.curve.representation.value
                != replay_state.selectedCurveRepresentation
            ):
                raise ReportInputError("final curve representation conflicts with replay state")
            validation = final_profile.curveValidationSummary
            if (
                replay_state.selectedCurveCompilerVersion is not None
                and validation is not None
                and validation.compilerVersion != replay_state.selectedCurveCompilerVersion
            ):
                raise ReportInputError("final curve compiler version conflicts with replay state")


def _pace_profile_context(
    state: HistoricalSessionState,
    profile: ApprovedPaceProfileVersion | None,
) -> PaceProfileContextV1_1:
    if profile is None:
        return PaceProfileContextV1_1(
            status=MetricStatus.MISSING_TARGET,
            paceProfileId=state.selectedPaceProfileId,
            paceProfileVersion=state.selectedPaceProfileVersion,
            paceProfileSource=state.selectedPaceProfileSource,
            paceProfileType=state.selectedPaceProfileType,
            coachLocked=state.profileCoachLocked,
            targetTotalTimeSec=state.selectedProfileTargetTotalTimeSec,
        )
    if isinstance(profile, ApprovedContinuousPaceProfile):
        provenance = profile.curveProvenance
        return PaceProfileContextV1_1(
            status=MetricStatus.AVAILABLE,
            paceProfileId=profile.profileId,
            paceProfileVersion=profile.profileVersion,
            paceProfileSource=profile.source.value,
            paceProfileType=profile.profileType.value,
            coachLocked=profile.coachLocked,
            targetTotalTimeSec=profile.targetTimeConstraint.targetTotalTimeSec,
            targetSplitTimesSec=provenance.targetSplitTimesSec,
            predictedSplitTimesSec=provenance.predictedSplitTimesSec,
            predictedNextSplitTimeSec=provenance.predictedNextSplitTimeSec,
            predictedNextRepeatTimeSec=provenance.predictedNextRepeatTimeSec,
            uncertaintyP10=provenance.uncertaintyP10,
            uncertaintyP50=provenance.uncertaintyP50,
            uncertaintyP90=provenance.uncertaintyP90,
        )
    return PaceProfileContextV1_1(
        status=MetricStatus.AVAILABLE,
        paceProfileId=profile.profileId,
        paceProfileVersion=profile.profileVersion,
        paceProfileSource=profile.source.value,
        paceProfileType=profile.profileType.value,
        coachLocked=profile.coachLocked,
        targetTotalTimeSec=profile.targetTotalTimeSec,
    )


def build_session_report(
    *,
    replay_state: HistoricalSessionState,
    events: Sequence[EventEnvelope],
    workout: AnyWorkoutTemplate,
    pace_profile: ApprovedPaceProfileVersion | None,
    compiled_timeline: PaceTimeline | None,
    observations: Sequence[SessionObservation] = (),
    sensor_samples: Sequence[SensorObservation] = (),
    report_context: ReportBuildContext,
) -> SessionReportV1_1:
    """Build a pure deterministic report from historical replay and explicit inputs."""
    if not events:
        raise ReportInputError("report construction requires a non-empty event stream")
    replayed = replay_session(events, expected_session_id=replay_state.sessionId).state
    if replayed != replay_state:
        raise ReplayStateMismatchError(
            "supplied replay_state differs from a fresh replay of the canonical event stream"
        )
    planned_distance = _planned_distance(workout)
    _validate_report_inputs(
        replay_state=replay_state,
        events=events,
        workout=workout,
        pace_profile=pace_profile,
        compiled_timeline=compiled_timeline,
        report_context=report_context,
        planned_distance=planned_distance,
    )

    event_digest = event_digest_sha256(events)
    workout_digest = canonical_digest_sha256(workout)
    initial_profile_digest = (
        canonical_digest_sha256(pace_profile) if pace_profile is not None else None
    )
    timeline_digest = (
        canonical_digest_sha256(compiled_timeline) if compiled_timeline is not None else None
    )
    registry_digest = canonical_digest_sha256(report_context.profileRegistry)
    observation_digest = canonical_digest_sha256(observations)
    sensor_digest = canonical_digest_sha256(sensor_samples)
    policy_digest = canonical_digest_sha256(_analytics_policy_material(report_context))
    report_input_digest = canonical_digest_sha256(
        {
            "eventDigestSha256": event_digest,
            "workoutDigestSha256": workout_digest,
            "initialPaceProfileDigestSha256": initial_profile_digest,
            "compiledTimelineDigestSha256": timeline_digest,
            "profileRegistryDigestSha256": registry_digest,
            "observationDigestSha256": observation_digest,
            "sensorObservationDigestSha256": sensor_digest,
            "analyticsPolicyDigestSha256": policy_digest,
        }
    )
    completion_ratio = (
        min(1.0, replay_state.officialCompletedDistanceM / planned_distance)
        if replay_state.officialCompletedDistanceM is not None and planned_distance > 0
        else None
    )
    completion_status = _completion_status(replay_state)
    last_verified_wall = None
    if replay_state.verifiedSplits and replay_state.poolLengthM is not None:
        last_verified_wall = float(
            (replay_state.verifiedSplits[-1].lengthIndex + 1) * replay_state.poolLengthM
        )
    distance = DistanceSummary(
        status=(
            MetricStatus.AVAILABLE
            if replay_state.officialCompletedDistanceM is not None
            else MetricStatus.INSUFFICIENT_DATA
        ),
        plannedDistanceM=planned_distance,
        officialCompletedDistanceM=replay_state.officialCompletedDistanceM,
        completedLengthCount=replay_state.officialCompletedLengthCount,
        poolLengthM=replay_state.poolLengthM,
        completionRatio=completion_ratio,
        officialSplitCount=len(replay_state.recordedSplits),
        lastVerifiedWallM=last_verified_wall,
        partial=(
            completion_status is not ReportCompletionStatus.COMPLETED
            or completion_ratio is None
            or completion_ratio < 1.0 - 1e-9
        ),
    )
    timing = TimingSummary(
        status=(
            MetricStatus.AVAILABLE
            if replay_state.startedAtMs is not None
            else MetricStatus.NOT_APPLICABLE
        ),
        wallDurationMs=(
            replay_state.wallDurationMs if replay_state.startedAtMs is not None else None
        ),
        activeDurationMs=(
            replay_state.activeDurationMs if replay_state.startedAtMs is not None else None
        ),
        stoppedDurationMs=(
            replay_state.stoppedDurationMs if replay_state.startedAtMs is not None else None
        ),
        lifecyclePausedDurationMs=(
            replay_state.lifecyclePausedDurationMs if replay_state.startedAtMs is not None else None
        ),
        elapsedDurationMs=(
            replay_state.elapsedDurationMs if replay_state.startedAtMs is not None else None
        ),
        sessionStartMs=replay_state.startedAtMs,
        sessionEndMs=replay_state.endedAtMs,
    )

    split_result = build_split_analysis(
        replay_state=replay_state,
        events=events,
        pace_profile=pace_profile,
        compiled_timeline=compiled_timeline,
        report_context=report_context,
    )
    pacing = build_pacing_analysis(split_result, report_context)
    curve = build_continuous_curve_analysis(
        replay_state=replay_state,
        events=events,
        pace_profile=pace_profile,
        compiled_timeline=compiled_timeline,
        observations=observations,
        report_context=report_context,
        planned_distance_m=planned_distance,
    )
    stops = build_stop_pause_analysis(replay_state, events)
    resets = build_coach_reset_analysis(events, pace_profile, replay_state.poolLengthM)
    sensors = build_sensor_analysis(
        replay_state=replay_state,
        samples=sensor_samples,
        report_context=report_context,
    )
    final_profile = _final_profile(replay_state, pace_profile, report_context)
    pace_context = _pace_profile_context(replay_state, final_profile)

    warnings: list[str] = list(pacing.warningCodes)
    if distance.partial:
        warnings.append("PARTIAL_SESSION_REPORT")
    if not curve.available:
        warnings.append(curve.reason or "CONTINUOUS_CURVE_UNAVAILABLE")
    if replay_state.openStopPause is not None:
        warnings.append("OPEN_STOP_PAUSE_AT_REPORT_HORIZON")
    if report_context.simulatorSynthetic:
        warnings.append("SYNTHETIC_NOT_PERFORMANCE_EVIDENCE")
    data_quality = build_report_data_quality(
        event_stream_complete=(events[0].seq == 1 and events[-1].seq == len(events)),
        replay_valid=True,
        timing=timing,
        distance=distance,
        splits=split_result.analysis,
        curve=curve,
        sensors=sensors,
        target_profile_available=pace_context.status is MetricStatus.AVAILABLE,
        warning_codes=tuple(warnings),
    )

    dataset_ids: tuple[str, ...] = ()
    curve_origin = None
    evidence_level = None
    shape_source = None
    continuous_ground_truth = None
    profile_schema: str | None = None
    if isinstance(final_profile, ApprovedContinuousPaceProfile):
        profile_schema = final_profile.schemaVersion
        curve_provenance = final_profile.curveProvenance
        dataset_ids = curve_provenance.sourceDatasetAssetIds or ()
        curve_origin = (
            curve_provenance.curveOrigin.value if curve_provenance.curveOrigin is not None else None
        )
        evidence_level = (
            curve_provenance.curveEvidenceLevel.value
            if curve_provenance.curveEvidenceLevel is not None
            else None
        )
        shape_source = (
            curve_provenance.visualShapeSource.value
            if curve_provenance.visualShapeSource is not None
            else None
        )
        continuous_ground_truth = curve_provenance.continuousCurveGroundTruth
    elif final_profile is not None:
        profile_schema = "1.0"

    provenance = ReportProvenance(
        analyticsVersion=report_context.analyticsVersion,
        reportBuilderVersion=report_context.reportBuilderVersion,
        reportSchemaVersion="1.1",
        eventFirstSeq=events[0].seq,
        eventLastSeq=events[-1].seq,
        eventCount=len(events),
        eventDigestSha256=event_digest,
        workoutDigestSha256=workout_digest,
        initialPaceProfileDigestSha256=initial_profile_digest,
        compiledTimelineDigestSha256=timeline_digest,
        profileRegistryDigestSha256=registry_digest,
        observationDigestSha256=observation_digest,
        sensorObservationDigestSha256=sensor_digest,
        analyticsPolicyDigestSha256=policy_digest,
        reportInputDigestSha256=report_input_digest,
        workoutSchemaVersion=workout.schemaVersion,
        paceProfileSchemaVersion=profile_schema,
        paceProfileId=replay_state.selectedPaceProfileId,
        paceProfileVersion=replay_state.selectedPaceProfileVersion,
        paceProfileSource=replay_state.selectedPaceProfileSource,
        paceProfileType=replay_state.selectedPaceProfileType,
        curveRepresentation=replay_state.selectedCurveRepresentation,
        curveCompilerVersion=replay_state.selectedCurveCompilerVersion,
        datasetEvidenceAssetIds=dataset_ids,
        curveOrigin=curve_origin,
        curveEvidenceLevel=evidence_level,
        visualShapeSource=shape_source,
        continuousCurveGroundTruth=continuous_ground_truth,
        simulatorSynthetic=report_context.simulatorSynthetic,
        simulationRunId=report_context.simulationRunId,
        adherenceToleranceSec=report_context.adherenceToleranceSec,
        onTargetTolerancePct=report_context.onTargetTolerancePct,
        declineMinimumConsecutiveSplits=report_context.minimumConsecutiveDecliningSplits,
        declineMinimumPct=report_context.minimumDeclinePct,
    )
    draft = SessionReportV1_1(
        reportId="PENDING",
        reportVersion=report_context.reportVersion,
        sessionId=replay_state.sessionId,
        workoutId=replay_state.workoutRef or workout.name,
        reportGeneratedAtMs=replay_state.lastEventTimestampMs,
        createdFromLastSeq=replay_state.lastSeq,
        sessionSummary=SessionSummary(
            lifecycleState=replay_state.lifecycleState.value,
            completionStatus=completion_status,
            terminal=completion_status
            in {ReportCompletionStatus.COMPLETED, ReportCompletionStatus.ABORTED},
            recordedSplitCount=len(replay_state.recordedSplits),
            verifiedSplitCount=len(replay_state.verifiedSplits),
            stopPauseOpen=replay_state.openStopPause is not None,
            pendingCoachReset=replay_state.pendingCoachPacingReset is not None,
        ),
        timingSummary=timing,
        distanceSummary=distance,
        paceProfileContext=pace_context,
        splitAnalysis=split_result.analysis,
        pacingAnalysis=pacing,
        continuousCurveAnalysis=curve,
        stopPauseAnalysis=stops,
        coachResetAnalysis=resets,
        sensorAnalysis=sensors,
        dataQuality=data_quality,
        provenance=provenance,
    )
    return draft.model_copy(update={"reportId": deterministic_report_id(draft)})
