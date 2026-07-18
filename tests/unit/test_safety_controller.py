"""Commit 6 — SafetyController: deterministic gate, source rules, context validation."""

from __future__ import annotations

import math

import pytest

from contracts.enums import AdaptationMode, PaceRequestSource
from swimcore.control import (
    InvalidSafetyContextError,
    PaceChangeRequest,
    SafetyContext,
    SafetyController,
    SafetyDecision,
    SafetyReasonCode,
)


def _ctx(mode=AdaptationMode.bounded_auto, **kw) -> SafetyContext:
    base = dict(
        currentAppliedPaceSecPer100M=80.0,
        coachTargetPaceSecPer100M=82.0,
        adaptationMode=mode,
        fastestAllowedPaceSecPer100M=76.0,
        slowestAllowedPaceSecPer100M=90.0,
        maxChangePercentPerLength=5.0,
        currentWallDistanceM=100.0,
        isWallBoundary=True,
    )
    base.update(kw)
    return SafetyContext(**base)


SC = SafetyController()


def test_mode_off_abstains() -> None:
    d = SC.decide(PaceChangeRequest(81.0), _ctx(mode=AdaptationMode.off))
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.MODE_OFF in d.reasonCodes


def test_suggest_only_does_not_auto_apply() -> None:
    d = SC.decide(PaceChangeRequest(81.0), _ctx(mode=AdaptationMode.suggest_only))
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.SUGGEST_ONLY in d.reasonCodes


def test_bounded_auto_applies_valid_suggestion() -> None:
    d = SC.decide(PaceChangeRequest(81.0), _ctx())
    assert d.decision is SafetyDecision.APPLY
    assert d.appliedPaceSecPer100M == pytest.approx(81.0)


def test_fast_suggestion_bounded_by_fastest_limit() -> None:
    d = SC.decide(PaceChangeRequest(60.0), _ctx(maxChangePercentPerLength=100.0))
    assert d.decision is SafetyDecision.BOUNDED_APPLY
    assert d.appliedPaceSecPer100M == pytest.approx(76.0)
    assert SafetyReasonCode.BOUNDED_BY_FASTEST_LIMIT in d.reasonCodes


def test_slow_suggestion_bounded_by_slowest_limit() -> None:
    d = SC.decide(PaceChangeRequest(120.0), _ctx(maxChangePercentPerLength=100.0))
    assert d.decision is SafetyDecision.BOUNDED_APPLY
    assert d.appliedPaceSecPer100M == pytest.approx(90.0)
    assert SafetyReasonCode.BOUNDED_BY_SLOWEST_LIMIT in d.reasonCodes


def test_change_bounded_by_max_percentage() -> None:
    d = SC.decide(PaceChangeRequest(70.0), _ctx())
    assert d.decision is SafetyDecision.BOUNDED_APPLY
    assert d.appliedPaceSecPer100M == pytest.approx(76.0)
    assert SafetyReasonCode.BOUNDED_BY_MAX_CHANGE in d.reasonCodes


# --- source-based confidence / data-quality (2.11) ---
def test_ml_missing_confidence_abstains() -> None:
    d = SC.decide(
        PaceChangeRequest(81.0, source=PaceRequestSource.ML, inputDataQuality=0.9), _ctx()
    )
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.ML_CONFIDENCE_MISSING in d.reasonCodes


def test_ml_missing_data_quality_abstains() -> None:
    d = SC.decide(PaceChangeRequest(81.0, source=PaceRequestSource.ML, confidence=0.9), _ctx())
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.DATA_QUALITY_MISSING in d.reasonCodes


def test_ml_low_confidence_abstains() -> None:
    d = SC.decide(
        PaceChangeRequest(81.0, source=PaceRequestSource.ML, confidence=0.2, inputDataQuality=0.9),
        _ctx(),
    )
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.LOW_CONFIDENCE in d.reasonCodes


def test_coach_manual_does_not_require_ml_confidence() -> None:
    d = SC.decide(PaceChangeRequest(81.0, source=PaceRequestSource.COACH_MANUAL), _ctx())
    assert d.decision is SafetyDecision.APPLY


def test_rule_request_requires_data_quality() -> None:
    d = SC.decide(PaceChangeRequest(81.0, source=PaceRequestSource.RULE_BASED), _ctx())
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.DATA_QUALITY_MISSING in d.reasonCodes


def test_ml_cannot_override_coach_locked_profile() -> None:
    d = SC.decide(
        PaceChangeRequest(81.0, source=PaceRequestSource.ML, confidence=0.9, inputDataQuality=0.9),
        _ctx(coachLocked=True),
    )
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN


def test_not_at_wall_does_not_apply() -> None:
    d = SC.decide(PaceChangeRequest(81.0), _ctx(isWallBoundary=False))
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.NOT_AT_WALL_BOUNDARY in d.reasonCodes


def test_invalid_nan_infinity_rejected() -> None:
    for bad in (math.nan, math.inf, -math.inf, 0.0, -5.0):
        d = SC.decide(PaceChangeRequest(bad), _ctx())
        assert d.decision is SafetyDecision.REJECT
        assert SafetyReasonCode.INVALID_SUGGESTION in d.reasonCodes


def test_smaller_number_treated_as_faster() -> None:
    d = SC.decide(PaceChangeRequest(50.0), _ctx(maxChangePercentPerLength=100.0))
    assert d.appliedPaceSecPer100M == pytest.approx(76.0)


def test_heart_rate_only_rejected() -> None:
    d = SC.decide(PaceChangeRequest(81.0, heartRateOnly=True), _ctx())
    assert d.decision is SafetyDecision.REJECT
    assert SafetyReasonCode.HEART_RATE_ONLY_REJECTED in d.reasonCodes


def test_reason_codes_always_present() -> None:
    for req in (PaceChangeRequest(81.0), PaceChangeRequest(math.nan), PaceChangeRequest(60.0)):
        d = SC.decide(req, _ctx(maxChangePercentPerLength=100.0))
        assert len(d.reasonCodes) >= 1


def test_deterministic_repeated_decisions() -> None:
    a = SC.decide(PaceChangeRequest(70.0), _ctx())
    b = SC.decide(PaceChangeRequest(70.0), _ctx())
    assert a == b


# --- context validation (2.10) ---
def test_reversed_safety_bounds_rejected() -> None:
    with pytest.raises(InvalidSafetyContextError):
        SC.decide(
            PaceChangeRequest(81.0),
            _ctx(fastestAllowedPaceSecPer100M=95.0, slowestAllowedPaceSecPer100M=80.0),
        )


def test_nan_current_pace_rejected() -> None:
    with pytest.raises(InvalidSafetyContextError):
        SC.decide(PaceChangeRequest(81.0), _ctx(currentAppliedPaceSecPer100M=math.nan))


def test_invalid_threshold_ratio_rejected() -> None:
    with pytest.raises(InvalidSafetyContextError):
        SC.decide(PaceChangeRequest(81.0), _ctx(minConfidence=1.5))


def test_bounded_auto_requires_bounds() -> None:
    with pytest.raises(InvalidSafetyContextError):
        SC.decide(PaceChangeRequest(81.0), _ctx(fastestAllowedPaceSecPer100M=None))


def test_invalid_wall_distance_rejected() -> None:
    with pytest.raises(InvalidSafetyContextError):
        SC.decide(PaceChangeRequest(81.0), _ctx(currentWallDistanceM=-1.0))
