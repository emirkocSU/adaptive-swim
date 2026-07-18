"""Safety-controller profile authority and ML abstain reasons (§2.11, §12)."""

from __future__ import annotations

from contracts.enums import AdaptationMode, PaceRequestSource
from swimcore.control import PaceChangeRequest, SafetyContext, SafetyController
from swimcore.control.types import SafetyDecision, SafetyReasonCode

SC = SafetyController()


def _ctx(**over: object) -> SafetyContext:
    base: dict = {
        "currentAppliedPaceSecPer100M": 80.0,
        "coachTargetPaceSecPer100M": 80.0,
        "adaptationMode": AdaptationMode.bounded_auto,
        "fastestAllowedPaceSecPer100M": 70.0,
        "slowestAllowedPaceSecPer100M": 95.0,
        "maxChangePercentPerLength": 5.0,
        "isWallBoundary": True,
    }
    base.update(over)
    return SafetyContext(**base)


def test_ml_missing_confidence_uses_distinct_reason() -> None:
    d = SC.decide(
        PaceChangeRequest(81.0, source=PaceRequestSource.ML, inputDataQuality=0.9), _ctx()
    )
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.ML_CONFIDENCE_MISSING in d.reasonCodes


def test_ml_missing_data_quality_uses_distinct_reason() -> None:
    d = SC.decide(PaceChangeRequest(81.0, source=PaceRequestSource.ML, confidence=0.9), _ctx())
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.DATA_QUALITY_MISSING in d.reasonCodes


def test_ml_with_confidence_and_quality_below_threshold_is_low_not_missing() -> None:
    d = SC.decide(
        PaceChangeRequest(81.0, source=PaceRequestSource.ML, confidence=0.1, inputDataQuality=0.9),
        _ctx(minConfidence=0.8),
    )
    assert SafetyReasonCode.LOW_CONFIDENCE in d.reasonCodes


def test_ml_cannot_override_coach_locked_profile_metadata() -> None:
    d = SC.decide(
        PaceChangeRequest(
            75.0, source=PaceRequestSource.ML, confidence=0.99, inputDataQuality=0.99
        ),
        _ctx(profileCoachLocked=True),
    )
    assert d.decision is SafetyDecision.ABSTAIN_USE_COACH_PLAN
    assert SafetyReasonCode.COACH_PROFILE_LOCKED in d.reasonCodes


def test_coach_manual_does_not_require_ml_confidence() -> None:
    d = SC.decide(PaceChangeRequest(81.0, source=PaceRequestSource.COACH_MANUAL), _ctx())
    assert d.decision in (SafetyDecision.APPLY, SafetyDecision.BOUNDED_APPLY)


def test_coach_manual_still_obeys_hard_bounds() -> None:
    d = SC.decide(
        PaceChangeRequest(50.0, source=PaceRequestSource.COACH_MANUAL),
        _ctx(maxChangePercentPerLength=99.0),
    )
    # 50 is faster than the fastest bound of 70 -> clamped to 70.
    assert d.appliedPaceSecPer100M == 70.0
    assert SafetyReasonCode.BOUNDED_BY_FASTEST_LIMIT in d.reasonCodes
