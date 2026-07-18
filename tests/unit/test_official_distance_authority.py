"""Official-distance authority and profile-session integration (§10, §11, §22.4)."""

from __future__ import annotations

import pytest

from contracts.commands import ArmSession, RecordSplit, StartSession
from swimcore.session import SessionWorkoutValidationError
from tests.unit._profile_helpers import (
    create_profile_session,
    load_profile,
    profile_aggregate,
    workout_1_1,
)


def _dive_profile():
    return load_profile("200m_25m_dive_133s_model_approved.json")


def test_profile_session_records_selected_metadata() -> None:
    agg, _ = profile_aggregate(_dive_profile(), workout_1_1())
    create_profile_session(agg)
    assert agg.selectedPaceProfileId == "prof-200-25-dive-133"
    assert agg.selectedPaceProfileSource == "COACH_APPROVED_MODEL"
    assert agg.poolLengthM == 25
    assert agg.defaultStartMode == "DIVE_START"
    assert agg.workoutGoal == "RACE_PACE"


def test_dive_start_official_distance_starts_at_zero() -> None:
    agg, _ = profile_aggregate(_dive_profile(), workout_1_1())
    create_profile_session(agg)
    # Before any wall split, the official completed distance is zero (dive starts at 0 m).
    assert agg.lastWallDistanceM == 0.0
    assert len(agg.recordedSplits) == 0


def test_draft_model_profile_cannot_start_session() -> None:
    prof = _dive_profile().model_copy(update={"approvalStatus": "DRAFT"})
    agg, _ = profile_aggregate(prof, workout_1_1())
    with pytest.raises(SessionWorkoutValidationError):
        create_profile_session(agg)


def test_official_distance_comes_from_walls_not_leg_boundaries() -> None:
    # Official walls are 25 m in a 25 m pool; profile legs are also 25 m here, but the
    # official split accounting is driven by RecordSplit wall boundaries, not the profile.
    agg, clk = profile_aggregate(_dive_profile(), workout_1_1())
    create_profile_session(agg)
    clk.set(100)
    agg.handle(ArmSession(clientCommandId="arm", sessionId=agg.sessionId))
    clk.set(200)
    agg.handle(StartSession(clientCommandId="start", sessionId=agg.sessionId))
    agg.handle(
        RecordSplit(
            clientCommandId="s0",
            sessionId=agg.sessionId,
            splitId="split-0",
            lengthIndex=0,
            wallTimestampMs=20000,
            source="TOUCHPAD",
            distanceM=25.0,
        )
    )
    assert agg.lastWallDistanceM == 25.0


def test_wearable_estimate_cannot_shorten_official_distance() -> None:
    # A 25 m length reported as 22 m (a non-wall boundary) is rejected: the wearable estimate
    # never rewrites official distance.
    agg, clk = profile_aggregate(_dive_profile(), workout_1_1())
    create_profile_session(agg)
    clk.set(100)
    agg.handle(ArmSession(clientCommandId="arm", sessionId=agg.sessionId))
    clk.set(200)
    agg.handle(StartSession(clientCommandId="start", sessionId=agg.sessionId))
    from swimcore.session import InvalidSplitBoundaryError

    with pytest.raises(InvalidSplitBoundaryError):
        agg.handle(
            RecordSplit(
                clientCommandId="s0",
                sessionId=agg.sessionId,
                splitId="split-0",
                lengthIndex=0,
                wallTimestampMs=20000,
                source="WEARABLE",
                distanceM=22.0,
            )
        )


def test_profile_distance_must_match_workout_distance() -> None:
    # A 100 m profile cannot run a 200 m workout (distance is compared against the workout,
    # not the profile's own total).
    prof = load_profile("100m_sprint_positive_split.json")  # 100 m profile
    wk = workout_1_1(distance=200)  # 200 m workout
    agg, _ = profile_aggregate(prof, wk)
    with pytest.raises(SessionWorkoutValidationError):
        create_profile_session(agg)


def test_profile_matching_distance_is_accepted() -> None:
    prof = load_profile("100m_sprint_positive_split.json")
    wk = workout_1_1(distance=100)
    agg, _ = profile_aggregate(prof, wk)
    create_profile_session(agg)
    assert agg.selectedPaceProfileId == prof.profileId
