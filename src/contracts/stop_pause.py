"""StopPause contracts.

The general runtime stop behaviour is **StopPause**. "Incident" is only a trigger
(``StopPauseTrigger.MANUAL_INCIDENT``).

The system does not force a precise "which metre did the swimmer stop at" at the contract
level. During a StopPause the ghost aligns to the swimmer (mid-pool allowed), but official
workout accounting happens at the next valid wall — ``wallReconciliationPending`` marks
that this reconciliation is still due. The stop reason is not labelled by the core; the
coach may annotate it later.

``StopPausePolicy`` is a *configuration* contract (coach-configurable). It may be carried
at session or workout-assignment level. Runtime logic that consumes it is written in a
later commit, not here.
"""

from __future__ import annotations

from pydantic import model_validator

from contracts._base import (
    NonEmptyStr,
    NonNegFloat,
    NonNegInt,
    PosFloat,
    StrictModel,
    approx_equal,
)
from contracts.enums import (
    AlignmentQuality,
    AlignmentSource,
    StopDetectionSource,
    StopPauseTrigger,
    StopSignalQuality,
    StopStartTimeQuality,
)


class StopPausePolicy(StrictModel):
    """Coach-configurable StopPause policy.

    The 10-second long-stop threshold is a *default hypothesis*, not a fixed core value.
    In Phase 1 the manual STOP/RESUME flow is the primary mode; automatic detection is
    only usable when explicitly enabled. ML or heart rate alone can never start a
    StopPause.
    """

    enabled: bool = True
    longStopThresholdSec: PosFloat = 10.0
    automaticDetectionEnabled: bool = False
    minimumDetectionQuality: StopSignalQuality = StopSignalQuality.HIGH


class StopPauseInterval(StrictModel):
    intervalId: NonEmptyStr
    sessionId: NonEmptyStr
    trigger: StopPauseTrigger

    startedAtMs: NonNegInt
    endedAtMs: NonNegInt | None = None
    durationSec: NonNegFloat | None = None

    # Workout context — deliberately optional; reconciled at the next wall.
    relatedSetIndex: NonNegInt | None = None
    relatedRepeatIndex: NonNegInt | None = None
    relatedLengthIndex: NonNegInt | None = None

    detectionSource: StopDetectionSource
    detectionQuality: StopSignalQuality = StopSignalQuality.UNKNOWN

    alignmentSource: AlignmentSource = AlignmentSource.UNKNOWN
    alignmentQuality: AlignmentQuality = AlignmentQuality.UNKNOWN
    stopStartTimeQuality: StopStartTimeQuality = StopStartTimeQuality.UNKNOWN

    #: True when the stop began mid-pool; official accounting is finalized at the next wall.
    wallReconciliationPending: bool = False

    notes: str | None = None
    createdBy: NonEmptyStr

    @model_validator(mode="after")
    def _validate_resolved_interval(self) -> StopPauseInterval:
        if self.endedAtMs is not None:
            if self.endedAtMs < self.startedAtMs:
                raise ValueError("endedAtMs must be >= startedAtMs")
            if self.durationSec is None:
                raise ValueError("a resolved interval (endedAtMs set) requires durationSec")
            expected = (self.endedAtMs - self.startedAtMs) / 1000.0
            if not approx_equal(self.durationSec, expected):
                raise ValueError(
                    "durationSec must match (endedAtMs - startedAtMs) / 1000 "
                    f"(got {self.durationSec}, expected {expected})"
                )
        return self
