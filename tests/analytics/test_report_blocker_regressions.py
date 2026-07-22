from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from analytics import (
    ReportBuildContext,
    SensorObservation,
    SessionObservation,
    build_session_report,
    decode_session_report,
    encode_session_report,
)
from analytics.curves import build_continuous_curve_analysis
from analytics.errors import ObservationValidationError, ReportInputError
from analytics.stops import build_stop_pause_analysis
from contracts.enums import PaceProfileSource
from contracts.pace_profiles import ApprovedPaceProfile
from persistence.session_report_store import SessionReportStore, SessionReportStoreError
from simulator.harness import SimulationResult, compile_ghost_timeline
from simulator.scenarios import SCENARIO_BY_NAME
from swimcore.pacing.types import PaceTimeline
from swimcore.replay.reducer import replay_session
from swimtools.build_session_report import main as build_report_main
from tests.replay._stream_helpers import StreamBuilder
from tests.unit._analytics_helpers import case, profile, workout


def _build_with_observations(observations: tuple[SessionObservation, ...], **context_kwargs):
    wk, prof, events, state, timeline = case()
    return build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        observations=observations,
        report_context=ReportBuildContext(**context_kwargs),
    )


def test_cli_coach_reset_uses_replacement_profile_registry(
    tmp_path: Path, analytics_results: dict[str, SimulationResult]
) -> None:
    result = analytics_results["coach-continuous-curve-reset"]
    scenario = SCENARIO_BY_NAME["coach-continuous-curve-reset"]()
    assert scenario.replacementProfile is not None
    workout_path = tmp_path / "workout.json"
    initial_path = tmp_path / "initial.json"
    replacement_path = tmp_path / "replacement.json"
    output = tmp_path / "report.json"
    workout_path.write_text(json.dumps(scenario.workout.model_dump(mode="json")), encoding="utf-8")
    initial_path.write_text(json.dumps(scenario.profile.model_dump(mode="json")), encoding="utf-8")
    replacement_path.write_text(
        json.dumps(scenario.replacementProfile.model_dump(mode="json")), encoding="utf-8"
    )

    assert (
        build_report_main(
            [
                "--journal",
                str(result.journalPath),
                "--workout",
                str(workout_path),
                "--pace-profile",
                str(initial_path),
                "--replacement-pace-profile",
                str(replacement_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = decode_session_report(output.read_bytes())
    assert report.paceProfileContext.paceProfileId == "resetrepl100"
    assert report.paceProfileContext.paceProfileSource == "COACH_APPROVED_MODEL"
    assert report.paceProfileContext.coachLocked is True
    assert report.provenance.paceProfileId == "resetrepl100"
    reset_from = report.coachResetAnalysis.resets[0].appliedWallDistanceM
    assert reset_from is not None
    post_reset = [item for item in report.splitAnalysis.splits if item.fromM >= reset_from]
    assert post_reset
    assert all(item.targetStatus.value == "AVAILABLE" for item in post_reset)
    assert all(item.profileId == "resetrepl100" for item in post_reset)


def test_cli_coach_reset_rejects_missing_replacement_registry(
    tmp_path: Path, analytics_results: dict[str, SimulationResult]
) -> None:
    result = analytics_results["coach-continuous-curve-reset"]
    scenario = SCENARIO_BY_NAME["coach-continuous-curve-reset"]()
    workout_path = tmp_path / "workout.json"
    initial_path = tmp_path / "initial.json"
    output = tmp_path / "report.json"
    workout_path.write_text(json.dumps(scenario.workout.model_dump(mode="json")), encoding="utf-8")
    initial_path.write_text(json.dumps(scenario.profile.model_dump(mode="json")), encoding="utf-8")

    assert (
        build_report_main(
            [
                "--journal",
                str(result.journalPath),
                "--workout",
                str(workout_path),
                "--pace-profile",
                str(initial_path),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()


def test_report_id_changes_with_observation_and_policy_content() -> None:
    observation_a = (
        SessionObservation(timestampMs=0, estimatedDistanceM=0.0),
        SessionObservation(timestampMs=40_000, estimatedDistanceM=50.0),
        SessionObservation(timestampMs=80_000, estimatedDistanceM=100.0),
    )
    observation_b = (
        SessionObservation(timestampMs=0, estimatedDistanceM=0.0),
        SessionObservation(timestampMs=40_000, estimatedDistanceM=40.0),
        SessionObservation(timestampMs=80_000, estimatedDistanceM=100.0),
    )
    first = _build_with_observations(observation_a)
    second = _build_with_observations(observation_b)
    assert first.reportId != second.reportId
    assert encode_session_report(first) != encode_session_report(second)

    wk, prof, events, state, timeline = case((20_000, 40_500, 60_500, 80_500))
    strict = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        report_context=ReportBuildContext(adherenceToleranceSec=0.1),
    )
    lenient = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        report_context=ReportBuildContext(adherenceToleranceSec=1.0),
    )
    assert strict.reportId != lenient.reportId
    assert (
        strict.splitAnalysis.aggregate.targetPaceAdherenceRatio
        != lenient.splitAnalysis.aggregate.targetPaceAdherenceRatio
    )

    sensor_a = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        sensor_samples=(SensorObservation(timestampMs=0, heartRateBpm=120.0),),
        report_context=ReportBuildContext(),
    )
    sensor_b = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        sensor_samples=(SensorObservation(timestampMs=0, heartRateBpm=130.0),),
        report_context=ReportBuildContext(),
    )
    assert sensor_a.reportId != sensor_b.reportId

    renamed_report = build_session_report(
        replay_state=state,
        events=events,
        workout=wk.model_copy(update={"name": "analytics-100-copy"}),
        pace_profile=prof,
        compiled_timeline=timeline,
        report_context=ReportBuildContext(),
    )
    profile_metadata_report = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof.model_copy(update={"createdAtMs": 1}),
        compiled_timeline=timeline,
        report_context=ReportBuildContext(),
    )
    assert renamed_report.reportId != strict.reportId
    assert profile_metadata_report.reportId != strict.reportId


def test_report_schema_version_is_fixed_to_1_1() -> None:
    with pytest.raises(ValueError, match="reportSchemaVersion must be 1.1"):
        ReportBuildContext(reportSchemaVersion="9.9")  # type: ignore[arg-type]


def test_report_builder_rejects_workout_profile_timeline_mismatches() -> None:
    wk, prof, events, state, timeline = case()
    raw = prof.model_dump(mode="json")
    raw["targetTotalTimeSec"] = 160.0
    raw["legs"] = [
        {
            "legIndex": 0,
            "fromM": 0,
            "toM": 200,
            "targetDurationSec": 160.0,
            "phaseType": "SURFACE_SWIM",
        }
    ]
    too_long = ApprovedPaceProfile.model_validate(raw)
    with pytest.raises(ReportInputError, match="profile distance"):
        build_session_report(
            replay_state=state,
            events=events,
            workout=wk,
            pace_profile=too_long,
            compiled_timeline=timeline,
            report_context=ReportBuildContext(),
        )

    wrong_timeline = PaceTimeline(
        totalDistanceM=200.0,
        totalActiveDurationSec=timeline.totalActiveDurationSec,
        intervals=timeline.intervals,
    )
    with pytest.raises(ReportInputError, match="timeline distance"):
        build_session_report(
            replay_state=state,
            events=events,
            workout=wk,
            pace_profile=prof,
            compiled_timeline=wrong_timeline,
            report_context=ReportBuildContext(),
        )

    wrong_interval = replace(timeline.intervals[0], profileId="other-profile")
    wrong_identity_timeline = replace(timeline, intervals=(wrong_interval,))
    with pytest.raises(ReportInputError, match="timeline profile id"):
        build_session_report(
            replay_state=state,
            events=events,
            workout=wk,
            pace_profile=prof,
            compiled_timeline=wrong_identity_timeline,
            report_context=ReportBuildContext(),
        )

    wrong_source = prof.model_copy(update={"source": PaceProfileSource.COACH_APPROVED_MODEL})
    with pytest.raises(ReportInputError, match="initial profile source"):
        build_session_report(
            replay_state=state,
            events=events,
            workout=wk,
            pace_profile=wrong_source,
            compiled_timeline=timeline,
            report_context=ReportBuildContext(),
        )


def test_out_of_session_observations_are_rejected() -> None:
    with pytest.raises(ObservationValidationError, match="outside session horizon"):
        _build_with_observations(
            (
                SessionObservation(timestampMs=100_000, estimatedDistanceM=0.0),
                SessionObservation(timestampMs=120_000, estimatedDistanceM=50.0),
                SessionObservation(timestampMs=140_000, estimatedDistanceM=100.0),
            )
        )


def test_velocity_only_trusted_observations_are_integrated() -> None:
    report = _build_with_observations(
        (
            SessionObservation(timestampMs=0, smoothedVelocityMps=1.25),
            SessionObservation(timestampMs=20_000, smoothedVelocityMps=1.25),
            SessionObservation(timestampMs=40_000, smoothedVelocityMps=1.25),
            SessionObservation(timestampMs=60_000, smoothedVelocityMps=1.25),
            SessionObservation(timestampMs=80_000, smoothedVelocityMps=1.25),
        )
    )
    assert report.continuousCurveAnalysis.available is True
    assert report.continuousCurveAnalysis.curveCoverageRatio == pytest.approx(1.0)
    assert report.continuousCurveAnalysis.curveDeviationMean == pytest.approx(0.0, abs=1e-6)


def test_velocity_only_integration_excludes_stopped_time() -> None:
    wk = workout()
    prof = profile()
    builder = (
        StreamBuilder()
        .created(
            0,
            pool=25,
            selectedPaceProfileId=prof.profileId,
            selectedPaceProfileVersion=prof.profileVersion,
            selectedPaceProfileSource=prof.source.value,
            selectedPaceProfileType=prof.profileType.value,
            profileCoachLocked=prof.coachLocked,
            selectedProfileTargetTotalTimeSec=prof.targetTotalTimeSec,
        )
        .armed(0)
        .started(0)
        .split(0, 20_000)
        .stop_started(started_at=25_000, confirmed_at=35_000, pending=True)
        .stop_resolved(started_at=25_000, ended_at=45_000, pending=True)
        .split(1, 60_000)
        .split(2, 80_000)
        .split(3, 100_000)
        .completed(100_000)
    )
    events = tuple(builder.events)
    state = replay_session(events).state
    timeline = compile_ghost_timeline(prof, wk)
    report = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        observations=tuple(
            SessionObservation(timestampMs=timestamp, smoothedVelocityMps=1.25)
            for timestamp in (0, 20_000, 40_000, 60_000, 80_000, 100_000)
        ),
        report_context=ReportBuildContext(),
    )
    assert report.continuousCurveAnalysis.available is True
    assert report.continuousCurveAnalysis.curveCoverageRatio == pytest.approx(1.0)
    assert report.continuousCurveAnalysis.curveDeviationMean == pytest.approx(0.0, abs=1e-6)


def test_stop_pause_reconciliation_is_pending_until_next_wall() -> None:
    prof = profile()
    builder = (
        StreamBuilder()
        .created(
            0,
            pool=25,
            selectedPaceProfileId=prof.profileId,
            selectedPaceProfileVersion=prof.profileVersion,
            selectedPaceProfileSource=prof.source.value,
            selectedPaceProfileType=prof.profileType.value,
            profileCoachLocked=prof.coachLocked,
            selectedProfileTargetTotalTimeSec=prof.targetTotalTimeSec,
        )
        .armed(0)
        .started(0)
        .split(0, 20_000)
        .stop_started(started_at=25_000, confirmed_at=35_000, pending=True)
        .stop_resolved(started_at=25_000, ended_at=45_000, pending=True)
    )
    pending_state = replay_session(tuple(builder.events)).state
    pending = build_stop_pause_analysis(pending_state, tuple(builder.events))
    assert pending.wallReconciliationCount == 0
    assert pending.pendingWallReconciliationCount == 1
    assert pending.intervals[0].reconciledAtWallM is None
    assert pending.intervals[0].wallReconciliationCompleted is False
    assert pending.intervals[0].wallReconciliationPendingAtReport is True

    builder.split(1, 60_000)
    reconciled_state = replay_session(tuple(builder.events)).state
    reconciled = build_stop_pause_analysis(reconciled_state, tuple(builder.events))
    assert reconciled.wallReconciliationCount == 1
    assert reconciled.pendingWallReconciliationCount == 0
    assert reconciled.intervals[0].reconciledAtWallM == 50.0
    assert reconciled.intervals[0].wallReconciliationCompleted is True


def test_planned_rest_does_not_dilute_low_quality_ratio() -> None:
    wk, prof, events, state, timeline = case()
    observations = [
        SessionObservation(timestampMs=0, estimatedDistanceM=0.0),
        SessionObservation(timestampMs=20_000, estimatedDistanceM=25.0, quality="LOW"),
        SessionObservation(timestampMs=40_000, estimatedDistanceM=50.0),
        SessionObservation(timestampMs=80_000, estimatedDistanceM=100.0),
    ]
    observations.extend(
        SessionObservation(
            timestampMs=41_000 + index,
            estimatedDistanceM=50.0,
            quality="HIGH",
            plannedRest=True,
        )
        for index in range(100)
    )
    observations.sort(key=lambda item: item.timestampMs)
    result = build_continuous_curve_analysis(
        replay_state=state,
        events=events,
        pace_profile=prof,
        compiled_timeline=timeline,
        observations=tuple(observations),
        report_context=ReportBuildContext(maximumLowQualityObservationRatio=0.05),
        planned_distance_m=100.0,
    )
    assert result.available is False
    assert result.reason == "LOW_QUALITY_OBSERVATION_COVERAGE"


def test_report_store_rejects_noncanonical_json(tmp_path: Path) -> None:
    value = _build_with_observations(())
    canonical = encode_session_report(value)
    pretty = json.dumps(json.loads(canonical), indent=2, sort_keys=True).encode("utf-8")
    with pytest.raises(SessionReportStoreError, match="not canonical"):
        SessionReportStore(tmp_path).write(value.reportId, pretty)


def test_absent_directional_split_extrema_are_none() -> None:
    wk, prof, events, state, timeline = case((19_000, 38_000, 57_000, 76_000))
    ahead = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        report_context=ReportBuildContext(),
    ).splitAnalysis.aggregate
    assert ahead.maximumPositiveSplitErrorSec is None
    assert ahead.maximumNegativeSplitErrorSec == pytest.approx(-1.0)

    wk, prof, events, state, timeline = case((21_000, 42_000, 63_000, 84_000))
    behind = build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        report_context=ReportBuildContext(),
    ).splitAnalysis.aggregate
    assert behind.maximumPositiveSplitErrorSec == pytest.approx(1.0)
    assert behind.maximumNegativeSplitErrorSec is None
