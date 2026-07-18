"""Immutable domain types for the pace-math engine.

These are self-contained value objects (frozen dataclasses) — they do not wrap or mutate
Pydantic contract models. ``EPSILON`` is the single float tolerance for the whole engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Central float comparison tolerance for the pace-math engine.
EPSILON: float = 1e-9


@dataclass(frozen=True, slots=True)
class PacePoint:
    distanceM: float
    elapsedActiveSec: float
    paceSecPer100M: float


@dataclass(frozen=True, slots=True)
class PaceInterval:
    """One expanded pace segment with resolved linear endpoints (global coordinates).

    ``startPaceSecPer100M`` / ``endPaceSecPer100M`` are the resolved curve endpoints
    (sec/100m; smaller = faster), regardless of the original mode name.
    """

    fromM: float
    toM: float
    startPaceSecPer100M: float
    endPaceSecPer100M: float
    mode: str
    activeDurationSec: float
    #: Provenance on the workout structure (2.14): which block/repeat/segment produced this.
    blockIndex: int = 0
    repeatIndex: int = 0
    segmentIndex: int = 0
    profileLegIndex: int | None = None
    #: Approved-profile provenance (ADR-034); populated by the profile compiler path.
    startMode: str | None = None
    profileId: str | None = None
    profileSource: str | None = None
    profileType: str | None = None
    phaseType: str | None = None

    @property
    def lengthM(self) -> float:
        return self.toM - self.fromM


@dataclass(frozen=True, slots=True)
class PaceTimeline:
    totalDistanceM: float
    totalActiveDurationSec: float
    intervals: tuple[PaceInterval, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DistanceAtTimeResult:
    elapsedActiveSec: float
    distanceM: float
    paceSecPer100M: float
    clamped: bool = False


@dataclass(frozen=True, slots=True)
class TimeAtDistanceResult:
    distanceM: float
    elapsedActiveSec: float
    paceSecPer100M: float
