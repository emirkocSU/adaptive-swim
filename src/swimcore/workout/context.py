"""Validation context.

Pure input carrier for rules that need external facts (supported schema versions, known
references, capabilities, limits). Everything is an explicit input; no rule ever imports a
DB, repository, or device. When the context is absent, context-dependent rules degrade to
a documented WARNING rather than failing silently.
"""

from __future__ import annotations

from contracts._base import StrictModel


class WorkoutValidationContext(StrictModel):
    supportedSchemaVersions: frozenset[str] = frozenset({"1.0"})
    maxTotalWorkoutDistanceM: int | None = None
    completedSessionIds: frozenset[str] = frozenset()
    knownCoachBenchmarkProfileRefs: frozenset[str] = frozenset()
    supportedFeedbackCapabilities: frozenset[str] = frozenset(
        {"showGhost", "showGapAtWall", "showContinuousGap"}
    )
    #: When True, a segment boundary that does not land on a wall is an ERROR (else WARNING).
    strictSegmentBoundaryMode: bool = False
