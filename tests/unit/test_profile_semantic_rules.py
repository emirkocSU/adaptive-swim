"""Approved-profile semantic rule-code emission (§6/§21 fix)."""

from __future__ import annotations

from contracts.enums import StartMode, Stroke
from swimcore.workout import RuleCode, validate_approved_pace_profile
from tests.unit._profile_helpers import load_profile


def _issues(profile, **over):
    kwargs = {
        "pool_length_m": profile.poolLengthM,
        "resolved_start_mode": profile.startMode,
        "stroke": profile.stroke,
        "workout_distance_m": profile.totalDistanceM,
    }
    kwargs.update(over)
    return validate_approved_pace_profile(profile, **kwargs)


def _codes(issues):
    return {i.rule for i in issues}


def test_valid_profile_has_no_issues() -> None:
    p = load_profile("200m_25m_dive_133s_model_approved.json")
    assert _issues(p) == []


def test_pool_mismatch_emits_issue() -> None:
    p = load_profile("200m_25m_dive_133s_model_approved.json")
    assert RuleCode.PACE_PROFILE_POOL_MISMATCH.value in _codes(_issues(p, pool_length_m=50))


def test_start_mode_mismatch_emits_issue() -> None:
    p = load_profile("200m_25m_dive_133s_model_approved.json")
    codes = _codes(_issues(p, resolved_start_mode=StartMode.IN_WATER_PUSH_START))
    assert RuleCode.PACE_PROFILE_START_MODE_MISMATCH.value in codes


def test_stroke_mismatch_emits_issue() -> None:
    p = load_profile("200m_25m_dive_133s_model_approved.json")
    assert RuleCode.PACE_PROFILE_STROKE_MISMATCH.value in _codes(
        _issues(p, stroke=Stroke.butterfly)
    )


def test_distance_coverage_gap_emits_issue() -> None:
    p = load_profile("200m_25m_dive_133s_model_approved.json")
    codes = _codes(_issues(p, workout_distance_m=400.0))
    assert RuleCode.PACE_PROFILE_COVERAGE_GAP.value in codes


def test_not_approved_profile_emits_issue() -> None:
    p = load_profile("200m_25m_dive_133s_model_approved.json").model_copy(
        update={"approvalStatus": "DRAFT"}
    )
    assert RuleCode.PACE_PROFILE_NOT_APPROVED.value in _codes(_issues(p))
