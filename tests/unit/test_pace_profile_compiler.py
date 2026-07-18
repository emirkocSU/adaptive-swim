"""Deterministic approved-profile compilation (§9, §22.3)."""

from __future__ import annotations

import pytest

from contracts.enums import StartMode, Stroke
from swimcore.pacing import ProfileCompilationError, compile_approved_pace_profile
from tests.unit._profile_helpers import load_profile


def _compile(name: str, **over: object):
    p = load_profile(name)
    kwargs: dict = {
        "pool_length_m": p.poolLengthM,
        "resolved_start_mode": p.startMode,
        "stroke": p.stroke,
        "total_distance_m": p.totalDistanceM,
    }
    kwargs.update(over)
    return compile_approved_pace_profile(p, **kwargs)


def test_profile_timeline_total_matches_target() -> None:
    p = load_profile("200m_25m_dive_133s_model_approved.json")
    tl = _compile("200m_25m_dive_133s_model_approved.json")
    assert tl.totalActiveDurationSec == pytest.approx(p.targetTotalTimeSec)
    assert tl.totalDistanceM == pytest.approx(200.0)


def test_same_total_different_start_mode_can_have_different_distribution() -> None:
    dive = _compile("200m_25m_dive_133s_model_approved.json")
    inw = _compile("200m_25m_inwater_133s_model_approved.json")
    assert dive.totalActiveDurationSec == pytest.approx(inw.totalActiveDurationSec)
    dive_legs = [iv.activeDurationSec for iv in dive.intervals]
    inw_legs = [iv.activeDurationSec for iv in inw.intervals]
    assert dive_legs != inw_legs


def test_sprint_positive_split_executes_fast_start_and_fade() -> None:
    tl = _compile("100m_sprint_positive_split.json")
    paces = [iv.startPaceSecPer100M for iv in tl.intervals]
    # positive split: each leg slower (larger sec/100m) than the previous
    assert all(paces[i] < paces[i + 1] for i in range(len(paces) - 1))


def test_final_acceleration_profile_executes_last_leg_faster() -> None:
    tl = _compile("800m_negative_split_profile.json")
    paces = [iv.startPaceSecPer100M for iv in tl.intervals]
    # negative split: last leg faster than first
    assert paces[-1] < paces[0]


def test_profile_compilation_is_deterministic() -> None:
    a = _compile("200m_25m_dive_133s_model_approved.json")
    b = _compile("200m_25m_dive_133s_model_approved.json")
    assert a == b


def test_profile_pool_must_match_workout_pool() -> None:
    with pytest.raises(ProfileCompilationError):
        _compile("200m_25m_dive_133s_model_approved.json", pool_length_m=50)


def test_profile_start_mode_must_match_resolved_start() -> None:
    with pytest.raises(ProfileCompilationError):
        _compile(
            "200m_25m_dive_133s_model_approved.json",
            resolved_start_mode=StartMode.IN_WATER_PUSH_START,
        )


def test_50m_profile_cannot_be_reused_as_25m() -> None:
    with pytest.raises(ProfileCompilationError):
        _compile("800m_negative_split_profile.json", pool_length_m=25)


def test_profile_stroke_mismatch_rejected() -> None:
    with pytest.raises(ProfileCompilationError):
        _compile("200m_25m_dive_133s_model_approved.json", stroke=Stroke.butterfly)


def test_profile_leg_vs_official_split_distinction() -> None:
    # Every compiled interval carries a profileLegIndex; leg count may exceed official walls.
    tl = _compile("200m_25m_dive_133s_model_approved.json")
    assert all(iv.profileLegIndex is not None for iv in tl.intervals)
    assert all(iv.mode == "approved_profile_leg" for iv in tl.intervals)
