"""Immutable inputs and centralized policies for deterministic report building."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.pace_profiles import ApprovedPaceProfile
from swimcore.pacing.types import PaceTimeline

ApprovedPaceProfileVersion = ApprovedPaceProfile | ApprovedContinuousPaceProfile
REPORT_SCHEMA_VERSION: Literal["1.1"] = "1.1"


@dataclass(frozen=True, slots=True)
class SessionObservation:
    """Trusted/optional swimmer observation supplied explicitly to analytics.

    Either ``estimatedDistanceM`` or ``smoothedVelocityMps`` may be supplied.  A
    velocity-only sequence is integrated only when it starts at the session start or has
    an explicit position anchor.  Estimated distance remains visual/analytical only and
    never creates official distance.
    """

    timestampMs: int
    estimatedDistanceM: float | None = None
    smoothedVelocityMps: float | None = None
    phaseType: str | None = None
    quality: str = "HIGH"
    trusted: bool = True
    plannedRest: bool = False
    source: str = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SensorObservation:
    timestampMs: int
    heartRateBpm: float | None = None
    paceSecPer100M: float | None = None
    strokeRateCyclesPerMin: float | None = None
    strokeLengthMPerCycle: float | None = None
    strokeIndex: float | None = None
    strokeCount: float | None = None
    quality: str = "HIGH"
    trusted: bool = True
    strokeDefinition: str | None = None


@dataclass(frozen=True, slots=True)
class ProfileRuntimeContext:
    profile: ApprovedPaceProfileVersion
    timeline: PaceTimeline


@dataclass(frozen=True, slots=True)
class ReportBuildContext:
    analyticsVersion: str = "analytics-1.0.0"
    reportBuilderVersion: str = "report-builder-1.0.0"
    reportSchemaVersion: Literal["1.1"] = REPORT_SCHEMA_VERSION
    reportVersion: str = "commit-9"
    adherenceToleranceSec: float = 0.75
    onTargetTolerancePct: float = 3.0
    curveAdherenceToleranceM: float = 1.0
    minimumTrustedCurveObservations: int = 3
    minimumCurveCoverageRatio: float = 0.25
    maximumLowQualityObservationRatio: float = 0.05
    minimumConsecutiveDecliningSplits: int = 2
    minimumDeclinePct: float = 2.0
    unexpectedCollapseMarginPct: float = 3.0
    minimumPacingShapeSplits: int = 3
    minimumSensorSamplesForTrend: int = 3
    simulatorSynthetic: bool = False
    simulationRunId: str | None = None
    profileRegistry: Mapping[tuple[str, str], ProfileRuntimeContext] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.reportSchemaVersion != REPORT_SCHEMA_VERSION:
            raise ValueError(
                f"Commit 9 reportSchemaVersion must be {REPORT_SCHEMA_VERSION}, "
                f"got {self.reportSchemaVersion!r}"
            )
        if not self.analyticsVersion or not self.reportBuilderVersion or not self.reportVersion:
            raise ValueError("analytics/report builder/report versions must be non-empty")
        non_negative = {
            "adherenceToleranceSec": self.adherenceToleranceSec,
            "onTargetTolerancePct": self.onTargetTolerancePct,
            "curveAdherenceToleranceM": self.curveAdherenceToleranceM,
            "minimumDeclinePct": self.minimumDeclinePct,
            "unexpectedCollapseMarginPct": self.unexpectedCollapseMarginPct,
        }
        for name, value in non_negative.items():
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        for name, value in {
            "minimumCurveCoverageRatio": self.minimumCurveCoverageRatio,
            "maximumLowQualityObservationRatio": self.maximumLowQualityObservationRatio,
        }.items():
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be within [0, 1]")
        for name, value in {
            "minimumTrustedCurveObservations": self.minimumTrustedCurveObservations,
            "minimumConsecutiveDecliningSplits": self.minimumConsecutiveDecliningSplits,
            "minimumPacingShapeSplits": self.minimumPacingShapeSplits,
            "minimumSensorSamplesForTrend": self.minimumSensorSamplesForTrend,
        }.items():
            if value < 1:
                raise ValueError(f"{name} must be at least 1")
