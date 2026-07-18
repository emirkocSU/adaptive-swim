"""Property-based invariants for the approved-profile mainline (§22.5)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from contracts.pace_profiles import ApprovedPaceProfile
from swimcore.pacing import (
    ProfileSelectionPolicy,
    compile_approved_pace_profile,
    select_live_pace_profile,
)

pytestmark = pytest.mark.property

_SOURCES = [
    "COACH_AUTHORED",
    "COACH_APPROVED_MODEL",
    "DEFAULT_MODEL_GENERATED",
    "TEMPLATE",
    "LEGACY_SEGMENTS",
]
_PRIORITY = {s: i for i, s in enumerate(_SOURCES)}


def _profile(source: str, pid: str) -> ApprovedPaceProfile:
    return ApprovedPaceProfile(
        profileId=pid,
        profileVersion="1",
        source=source,
        profileType="EVEN_PACE",
        approvalStatus="COACH_APPROVED",
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


@given(sources=st.lists(st.sampled_from(_SOURCES), min_size=1, max_size=6, unique=True))
def test_selection_is_deterministic_and_respects_priority(sources: list[str]) -> None:
    candidates = [_profile(s, f"p{i}") for i, s in enumerate(sources)]
    winner = select_live_pace_profile(
        candidates, ProfileSelectionPolicy(allowDefaultModelGenerated=True)
    )
    # winner has the highest authority present (lowest priority number), deterministically
    best = min(_PRIORITY[s] for s in sources)
    assert _PRIORITY[winner.source.value] == best
    # determinism: repeat call yields identical result
    again = select_live_pace_profile(
        candidates, ProfileSelectionPolicy(allowDefaultModelGenerated=True)
    )
    assert again.profileId == winner.profileId


@given(
    d0=st.integers(min_value=5, max_value=40),
    d1=st.integers(min_value=5, max_value=40),
)
def test_compiled_duration_equals_profile_total(d0: int, d1: int) -> None:
    total = float(d0 + d1)
    prof = ApprovedPaceProfile(
        profileId="p",
        profileVersion="1",
        source="COACH_AUTHORED",
        profileType="EVEN_PACE",
        approvalStatus="COACH_APPROVED",
        poolLengthM=25,
        startMode="DIVE_START",
        stroke="freestyle",
        workoutGoal="RACE_PACE",
        targetTotalTimeSec=total,
        legs=[
            {
                "legIndex": 0,
                "fromM": 0,
                "toM": 25,
                "targetDurationSec": float(d0),
                "phaseType": "SURFACE_SWIM",
            },
            {
                "legIndex": 1,
                "fromM": 25,
                "toM": 50,
                "targetDurationSec": float(d1),
                "phaseType": "FINISH",
            },
        ],
    )
    tl = compile_approved_pace_profile(
        prof,
        pool_length_m=25,
        resolved_start_mode=prof.startMode,
        stroke=prof.stroke,
        total_distance_m=50.0,
    )
    assert tl.totalActiveDurationSec == pytest.approx(prof.targetTotalTimeSec)
    # official distance covered is always the sum of leg distances (a pool-length multiple)
    assert tl.totalDistanceM == pytest.approx(50.0)
    assert tl.totalDistanceM % 25 == pytest.approx(0.0)
