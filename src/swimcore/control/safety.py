"""Deterministic SafetyController: the mandatory gate for every pace change.

Pure: it does not touch session state, events, the ghost, the clock, or persistence — it
only returns a decision. Smaller sec/100m is faster. ML output can never bypass this gate;
missing/low confidence or data quality falls back to the coach plan. Coach-manual requests
skip the confidence/quality gates but still obey the hard fastest/slowest bounds.
"""

from __future__ import annotations

import math

from contracts.enums import AdaptationMode, PaceRequestSource
from swimcore.control.errors import InvalidSafetyContextError
from swimcore.control.types import (
    ControlDecision,
    PaceChangeRequest,
    SafetyContext,
    SafetyDecision,
    SafetyReasonCode,
)

_PACE_MIN = 30.0
_PACE_MAX = 300.0


def _finite_positive(value: float) -> bool:
    return math.isfinite(value) and value > 0.0


def _pace_in_range(value: float) -> bool:
    return math.isfinite(value) and _PACE_MIN < value <= _PACE_MAX


class SafetyController:
    def _validate_context(self, request: PaceChangeRequest, context: SafetyContext) -> None:
        if not _pace_in_range(context.currentAppliedPaceSecPer100M):
            raise InvalidSafetyContextError("currentAppliedPaceSecPer100M out of range")
        if not _pace_in_range(context.coachTargetPaceSecPer100M):
            raise InvalidSafetyContextError("coachTargetPaceSecPer100M out of range")
        fastest = context.fastestAllowedPaceSecPer100M
        slowest = context.slowestAllowedPaceSecPer100M
        if fastest is not None and not _pace_in_range(fastest):
            raise InvalidSafetyContextError("fastestAllowedPaceSecPer100M out of range")
        if slowest is not None and not _pace_in_range(slowest):
            raise InvalidSafetyContextError("slowestAllowedPaceSecPer100M out of range")
        if fastest is not None and slowest is not None and fastest > slowest:
            raise InvalidSafetyContextError(
                f"reversed bounds: fastest {fastest} > slowest {slowest}"
            )
        mc = context.maxChangePercentPerLength
        if mc is not None and (not math.isfinite(mc) or mc <= 0.0):
            raise InvalidSafetyContextError("maxChangePercentPerLength must be finite and > 0")
        for ratio in (context.minConfidence, context.minDataQuality):
            if not (0.0 <= ratio <= 1.0):
                raise InvalidSafetyContextError("threshold ratios must be in [0, 1]")
        if not (math.isfinite(context.currentWallDistanceM) and context.currentWallDistanceM >= 0):
            raise InvalidSafetyContextError("currentWallDistanceM must be finite and >= 0")
        if context.adaptationMode is AdaptationMode.bounded_auto and (
            fastest is None or slowest is None or mc is None
        ):
            raise InvalidSafetyContextError(
                "bounded_auto requires fastest/slowest bounds and maxChangePercentPerLength"
            )

    def decide(self, request: PaceChangeRequest, context: SafetyContext) -> ControlDecision:
        self._validate_context(request, context)
        suggested = request.suggestedPaceSecPer100M
        coach = context.coachTargetPaceSecPer100M
        current = context.currentAppliedPaceSecPer100M

        def abstain(reason: SafetyReasonCode) -> ControlDecision:
            return ControlDecision(
                decision=SafetyDecision.ABSTAIN_USE_COACH_PLAN,
                suggestedPaceSecPer100M=suggested,
                appliedPaceSecPer100M=coach,
                reasonCodes=(reason, SafetyReasonCode.COACH_PLAN_FALLBACK),
                abstained=True,
            )

        if not _finite_positive(suggested):
            return ControlDecision(
                decision=SafetyDecision.REJECT,
                suggestedPaceSecPer100M=suggested,
                appliedPaceSecPer100M=current,
                reasonCodes=(SafetyReasonCode.INVALID_SUGGESTION,),
            )
        if request.heartRateOnly:
            return ControlDecision(
                decision=SafetyDecision.REJECT,
                suggestedPaceSecPer100M=suggested,
                appliedPaceSecPer100M=current,
                reasonCodes=(SafetyReasonCode.HEART_RATE_ONLY_REJECTED,),
            )

        # ML can never override a coach-locked profile (either the request-level lock flag
        # or the selected-profile lock metadata).
        if request.source is PaceRequestSource.ML and (
            context.coachLocked or context.profileCoachLocked
        ):
            return ControlDecision(
                decision=SafetyDecision.ABSTAIN_USE_COACH_PLAN,
                suggestedPaceSecPer100M=suggested,
                appliedPaceSecPer100M=coach,
                reasonCodes=(
                    SafetyReasonCode.COACH_PROFILE_LOCKED,
                    SafetyReasonCode.COACH_PLAN_FALLBACK,
                ),
                abstained=True,
            )

        if context.adaptationMode is AdaptationMode.off:
            return abstain(SafetyReasonCode.MODE_OFF)
        if context.adaptationMode is AdaptationMode.suggest_only:
            return abstain(SafetyReasonCode.SUGGEST_ONLY)
        if not context.isWallBoundary:
            return abstain(SafetyReasonCode.NOT_AT_WALL_BOUNDARY)

        # Source-based confidence / data-quality requirements. A *missing* field is a
        # distinct reason from a merely *low* one, so an ML request with no confidence /
        # data quality abstains explicitly (it must never fall through to APPLY).
        if request.source is PaceRequestSource.ML:
            if request.confidence is None:
                return abstain(SafetyReasonCode.ML_CONFIDENCE_MISSING)
            if request.inputDataQuality is None:
                return abstain(SafetyReasonCode.DATA_QUALITY_MISSING)
            if request.confidence < context.minConfidence:
                return abstain(SafetyReasonCode.LOW_CONFIDENCE)
            if request.inputDataQuality < context.minDataQuality:
                return abstain(SafetyReasonCode.LOW_DATA_QUALITY)
        elif request.source is PaceRequestSource.RULE_BASED:
            if request.inputDataQuality is None:
                return abstain(SafetyReasonCode.DATA_QUALITY_MISSING)
            if request.inputDataQuality < context.minDataQuality:
                return abstain(SafetyReasonCode.LOW_DATA_QUALITY)
            if request.confidence is not None and request.confidence < context.minConfidence:
                return abstain(SafetyReasonCode.LOW_CONFIDENCE)
        # COACH_MANUAL: no confidence/quality gate, but hard bounds still apply.

        applied = suggested
        reasons: list[SafetyReasonCode] = []
        if context.maxChangePercentPerLength is not None and _finite_positive(current):
            frac = context.maxChangePercentPerLength / 100.0
            lo = current * (1.0 - frac)
            hi = current * (1.0 + frac)
            if applied < lo:
                applied = lo
                reasons.append(SafetyReasonCode.BOUNDED_BY_MAX_CHANGE)
            elif applied > hi:
                applied = hi
                reasons.append(SafetyReasonCode.BOUNDED_BY_MAX_CHANGE)

        fastest = context.fastestAllowedPaceSecPer100M
        slowest = context.slowestAllowedPaceSecPer100M
        if fastest is not None and applied < fastest:
            applied = fastest
            reasons.append(SafetyReasonCode.BOUNDED_BY_FASTEST_LIMIT)
        if slowest is not None and applied > slowest:
            applied = slowest
            reasons.append(SafetyReasonCode.BOUNDED_BY_SLOWEST_LIMIT)

        if reasons:
            return ControlDecision(
                decision=SafetyDecision.BOUNDED_APPLY,
                suggestedPaceSecPer100M=suggested,
                appliedPaceSecPer100M=applied,
                reasonCodes=tuple(reasons),
                bounded=True,
            )
        return ControlDecision(
            decision=SafetyDecision.APPLY,
            suggestedPaceSecPer100M=suggested,
            appliedPaceSecPer100M=applied,
            reasonCodes=(SafetyReasonCode.APPLIED_WITHIN_BOUNDS,),
        )
