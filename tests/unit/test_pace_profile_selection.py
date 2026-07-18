"""Deterministic live pace-profile selection (§8, §22.3)."""

from __future__ import annotations

import pytest

from contracts.pace_profiles import ApprovedPaceProfile
from swimcore.pacing import (
    NoLiveEligiblePaceProfileError,
    ProfileSelectionPolicy,
    select_live_pace_profile,
)
from swimcore.pacing.profile_selection import AmbiguousPaceProfileSelectionError


def _profile(source: str, *, status: str = "COACH_APPROVED", pid: str = "p") -> ApprovedPaceProfile:
    return ApprovedPaceProfile(
        profileId=pid,
        profileVersion="1",
        source=source,
        profileType="EVEN_PACE",
        approvalStatus=status,
        poolLengthM=25,
        startMode="DIVE_START",
        stroke="freestyle",
        workoutGoal="RACE_PACE",
        targetTotalTimeSec=40.0,
        legs=[
            {
                "legIndex": 0,
                "fromM": 0,
                "toM": 25,
                "targetDurationSec": 20.0,
                "phaseType": "SURFACE_SWIM",
            },
            {
                "legIndex": 1,
                "fromM": 25,
                "toM": 50,
                "targetDurationSec": 20.0,
                "phaseType": "FINISH",
            },
        ],
    )


def test_coach_authored_beats_model_profile() -> None:
    winner = select_live_pace_profile(
        [_profile("COACH_APPROVED_MODEL", pid="m"), _profile("COACH_AUTHORED", pid="c")]
    )
    assert winner.profileId == "c"


def test_coach_approved_model_beats_default_model() -> None:
    winner = select_live_pace_profile(
        [
            _profile("DEFAULT_MODEL_GENERATED", pid="d"),
            _profile("COACH_APPROVED_MODEL", pid="m"),
        ],
        ProfileSelectionPolicy(allowDefaultModelGenerated=True),
    )
    assert winner.profileId == "m"


def test_default_model_requires_explicit_opt_in() -> None:
    with pytest.raises(NoLiveEligiblePaceProfileError):
        select_live_pace_profile([_profile("DEFAULT_MODEL_GENERATED")])
    winner = select_live_pace_profile(
        [_profile("DEFAULT_MODEL_GENERATED")],
        ProfileSelectionPolicy(allowDefaultModelGenerated=True),
    )
    assert winner.source.value == "DEFAULT_MODEL_GENERATED"


def test_draft_profile_is_not_eligible() -> None:
    with pytest.raises(NoLiveEligiblePaceProfileError):
        select_live_pace_profile([_profile("COACH_AUTHORED", status="DRAFT")])


def test_equal_priority_conflict_is_rejected() -> None:
    with pytest.raises(AmbiguousPaceProfileSelectionError):
        select_live_pace_profile(
            [_profile("COACH_AUTHORED", pid="a"), _profile("COACH_AUTHORED", pid="b")]
        )
