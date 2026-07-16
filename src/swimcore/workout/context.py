"""Validation context.

Pure input carrier for rules that need external facts (supported schema versions, known
references, capabilities, limits). Everything is an explicit input; no rule ever imports a
DB, repository, or device. When the context is absent, context-dependent rules degrade to a
documented WARNING rather than failing silently.
"""

from __future__ import annotations

from pydantic import field_validator

from contracts._base import StrictModel
from contracts.enums import FeedbackCapability

_DEFAULT_CAPABILITIES: frozenset[FeedbackCapability] = frozenset(FeedbackCapability)


class WorkoutValidationContext(StrictModel):
    supportedSchemaVersions: frozenset[str] = frozenset({"1.0"})
    maxTotalWorkoutDistanceM: int | None = None
    completedSessionIds: frozenset[str] = frozenset()
    knownCoachBenchmarkProfileRefs: frozenset[str] = frozenset()
    #: Typed capabilities only — unknown/typo strings are rejected.
    supportedFeedbackCapabilities: frozenset[FeedbackCapability] = _DEFAULT_CAPABILITIES
    #: When True, a segment boundary that does not land on a wall is an ERROR (else WARNING).
    strictSegmentBoundaryMode: bool = False

    @field_validator("supportedSchemaVersions")
    @classmethod
    def _schema_versions_not_empty(cls, v: frozenset[str]) -> frozenset[str]:
        if not v:
            raise ValueError("supportedSchemaVersions must not be empty")
        return v

    @field_validator("maxTotalWorkoutDistanceM")
    @classmethod
    def _max_distance_positive(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("maxTotalWorkoutDistanceM must be > 0")
        return v
