"""Pacing & safety contracts."""

from __future__ import annotations

from typing import Any

from contracts._base import NonNegInt, PaceValue, StrictModel, UnitRatio
from contracts.enums import (
    ControlAdaptationSource,
    ControlDecisionAction,
    GhostOperationalState,
    PaceTargetOrigin,
    ReasonCode,
)


class PaceTarget(StrictModel):
    effectiveFromLength: NonNegInt
    appliedPaceSecPer100M: PaceValue
    origin: PaceTargetOrigin
    controlDecisionId: str | None = None


class GhostState(StrictModel):
    distanceM: float
    speedMps: float
    operationalState: GhostOperationalState = GhostOperationalState.ACTIVE


class SwimmerState(StrictModel):
    state: str
    estimatedDistanceM: float | None = None
    confidence: UnitRatio = 0.0


class ControlDecision(StrictModel):
    """Explainability record: split → (inference?) → control decision → pace target."""

    inputsSnapshot: dict[str, Any]
    adaptationSource: ControlAdaptationSource
    decision: ControlDecisionAction
    reasonCode: ReasonCode
    suggestedPaceSecPer100M: PaceValue | None = None
    appliedPaceSecPer100M: PaceValue | None = None
    controlDecisionId: str | None = None
