from __future__ import annotations

from analytics import ReportBuildContext, build_session_report
from contracts.pace_profiles import ApprovedPaceProfile
from contracts.workout import WorkoutTemplateV1_1
from swimcore.pacing.profile_compiler import compile_live_profile
from swimcore.replay.reducer import replay_session
from swimcore.workout.start_mode import resolve_repeat_start_mode
from tests.replay._stream_helpers import StreamBuilder


def workout() -> WorkoutTemplateV1_1:
    return WorkoutTemplateV1_1.model_validate(
        {
            "schemaVersion": "1.1",
            "name": "analytics-100",
            "poolLengthM": 25,
            "stroke": "freestyle",
            "startPolicy": {"defaultMode": "IN_WATER_PUSH_START"},
            "workoutGoal": "RACE_PACE",
            "blocks": [
                {
                    "type": "repeat",
                    "repetitions": 1,
                    "distanceM": 100,
                    "rest": {"type": "none"},
                    "segments": [
                        {
                            "fromM": 0,
                            "toM": 100,
                            "mode": "even_pace",
                            "targetPaceSecPer100M": 80.0,
                        }
                    ],
                }
            ],
        }
    )


def profile() -> ApprovedPaceProfile:
    return ApprovedPaceProfile.model_validate(
        {
            "profileId": "analytics-profile",
            "profileVersion": "1",
            "source": "COACH_AUTHORED",
            "profileType": "EVEN_PACE",
            "approvalStatus": "COACH_APPROVED",
            "coachLocked": True,
            "poolLengthM": 25,
            "startMode": "IN_WATER_PUSH_START",
            "stroke": "freestyle",
            "workoutGoal": "RACE_PACE",
            "targetTotalTimeSec": 80.0,
            "legs": [
                {
                    "legIndex": 0,
                    "fromM": 0,
                    "toM": 100,
                    "targetDurationSec": 80.0,
                    "phaseType": "SURFACE_SWIM",
                }
            ],
        }
    )


def case(
    split_timestamps: tuple[int, ...] = (20_000, 40_000, 60_000, 80_000),
):
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
    )

    for index, timestamp in enumerate(split_timestamps):
        builder.split(index, timestamp)

    builder.completed(split_timestamps[-1])

    events = tuple(builder.events)
    state = replay_session(events).state
    timeline = compile_live_profile(
        prof,
        pool_length_m=25,
        resolved_start_mode=resolve_repeat_start_mode(wk, 0, 0),
        stroke=wk.stroke,
        total_distance_m=100.0,
    )

    return wk, prof, events, state, timeline


def report(
    split_timestamps: tuple[int, ...] = (20_000, 40_000, 60_000, 80_000),
):
    wk, prof, events, state, timeline = case(split_timestamps)

    return build_session_report(
        replay_state=state,
        events=events,
        workout=wk,
        pace_profile=prof,
        compiled_timeline=timeline,
        report_context=ReportBuildContext(),
    )
