"""Pure, immutable types for the deterministic SafetyController."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from contracts.enums import AdaptationMode, ControlAdaptationSource, PaceRequestSource


class SafetyDecision(StrEnum):
    APPLY = "APPLY"
    BOUNDED_APPLY = "BOUNDED_APPLY"
    ABSTAIN_USE_COACH_PLAN = "ABSTAIN_USE_COACH_PLAN"
    REJECT = "REJECT"


class SafetyReasonCode(StrEnum):
    MODE_OFF = "MODE_OFF"
    SUGGEST_ONLY = "SUGGEST_ONLY"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    LOW_DATA_QUALITY = "LOW_DATA_QUALITY"
    NOT_AT_WALL_BOUNDARY = "NOT_AT_WALL_BOUNDARY"
    BOUNDED_BY_FASTEST_LIMIT = "BOUNDED_BY_FASTEST_LIMIT"
    BOUNDED_BY_SLOWEST_LIMIT = "BOUNDED_BY_SLOWEST_LIMIT"
    BOUNDED_BY_MAX_CHANGE = "BOUNDED_BY_MAX_CHANGE"
    INVALID_SUGGESTION = "INVALID_SUGGESTION"
    COACH_PLAN_FALLBACK = "COACH_PLAN_FALLBACK"
    APPLIED_WITHIN_BOUNDS = "APPLIED_WITHIN_BOUNDS"
    HEART_RATE_ONLY_REJECTED = "HEART_RATE_ONLY_REJECTED"


@dataclass(frozen=True, slots=True)
class PaceChangeRequest:
    suggestedPaceSecPer100M: float
    source: PaceRequestSource = PaceRequestSource.COACH_MANUAL
    adaptationSource: ControlAdaptationSource = ControlAdaptationSource.rule_based
    confidence: float | None = None
    inputDataQuality: float | None = None
    #: True if the only justification for the change is heart rate (never sufficient alone).
    heartRateOnly: bool = False


@dataclass(frozen=True, slots=True)
class SafetyContext:
    currentAppliedPaceSecPer100M: float
    coachTargetPaceSecPer100M: float
    adaptationMode: AdaptationMode
    fastestAllowedPaceSecPer100M: float | None = None
    slowestAllowedPaceSecPer100M: float | None = None
    maxChangePercentPerLength: float | None = None
    currentWallDistanceM: float = 0.0
    isWallBoundary: bool = True
    minConfidence: float = 0.5
    minDataQuality: float = 0.5
    coachLocked: bool = False


@dataclass(frozen=True, slots=True)
class ControlDecision:
    decision: SafetyDecision
    suggestedPaceSecPer100M: float
    appliedPaceSecPer100M: float
    reasonCodes: tuple[SafetyReasonCode, ...] = field(default_factory=tuple)
    abstained: bool = False
    bounded: bool = False
