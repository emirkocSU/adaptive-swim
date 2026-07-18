"""ApprovedPaceProfile contract invariants (§7, §22.3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts.pace_profiles import ApprovedPaceProfile, PaceProfileLeg
from tests.unit._profile_helpers import load_profile


def _base(**over: object) -> dict:
    data: dict = {
        "profileId": "p",
        "profileVersion": "1",
        "source": "COACH_AUTHORED",
        "profileType": "EVEN_PACE",
        "approvalStatus": "COACH_APPROVED",
        "poolLengthM": 25,
        "startMode": "DIVE_START",
        "stroke": "freestyle",
        "workoutGoal": "RACE_PACE",
        "targetTotalTimeSec": 40.0,
        "legs": [
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
    }
    data.update(over)
    return data


def test_profile_legs_cover_exact_distance() -> None:
    p = ApprovedPaceProfile(**_base())
    assert p.totalDistanceM == 50.0


def test_first_leg_must_start_at_zero() -> None:
    bad = _base(
        legs=[
            {
                "legIndex": 0,
                "fromM": 5,
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
        ]
    )
    with pytest.raises(ValidationError):
        ApprovedPaceProfile(**bad)


def test_profile_leg_durations_sum_to_total() -> None:
    bad = _base(targetTotalTimeSec=99.0)
    with pytest.raises(ValidationError):
        ApprovedPaceProfile(**bad)


def test_profile_legs_reject_gap() -> None:
    bad = _base(
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
                "fromM": 30,
                "toM": 50,
                "targetDurationSec": 20.0,
                "phaseType": "FINISH",
            },
        ]
    )
    with pytest.raises(ValidationError):
        ApprovedPaceProfile(**bad)


def test_draft_profile_not_live_eligible() -> None:
    p = ApprovedPaceProfile(**_base(approvalStatus="DRAFT"))
    assert not p.is_live_eligible


def test_coach_locked_profile_is_live_eligible() -> None:
    p = ApprovedPaceProfile(**_base(approvalStatus="COACH_LOCKED", coachLocked=True))
    assert p.is_live_eligible


def test_coach_locked_without_eligible_status_rejected() -> None:
    with pytest.raises(ValidationError):
        ApprovedPaceProfile(**_base(approvalStatus="DRAFT", coachLocked=True))


def test_leg_pace_is_constant() -> None:
    leg = PaceProfileLeg(
        legIndex=0, fromM=0, toM=25, targetDurationSec=20.0, phaseType="SURFACE_SWIM"
    )
    assert leg.paceSecPer100M == pytest.approx(80.0)


def test_dive_and_inwater_fixtures_same_total_different_distribution() -> None:
    dive = load_profile("200m_25m_dive_133s_model_approved.json")
    inw = load_profile("200m_25m_inwater_133s_model_approved.json")
    assert dive.targetTotalTimeSec == pytest.approx(inw.targetTotalTimeSec)
    dive_legs = [leg.targetDurationSec for leg in dive.legs]
    inw_legs = [leg.targetDurationSec for leg in inw.legs]
    assert dive_legs != inw_legs  # same total, different split distribution
