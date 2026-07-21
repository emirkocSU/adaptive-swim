"""Pure historical session replay (Commit 7).

Replay produces a historical read model from typed domain events. It never executes
commands, never rewinds the runtime clocks, and performs no I/O — persistence lives one
layer above in the ``persistence`` package and may import this package, never the reverse.
"""

from swimcore.replay.errors import (
    EmptyReplayError,
    ReplayCommandBatchError,
    ReplayDuplicateEventIdError,
    ReplayDurationError,
    ReplayError,
    ReplaySequenceError,
    ReplaySessionMismatchError,
    ReplaySplitError,
    ReplayStopPauseError,
    ReplayTimestampError,
    ReplayTransitionError,
    UnsupportedReplaySchemaError,
)
from swimcore.replay.reducer import replay_session
from swimcore.replay.state import (
    HistoricalControlDecision,
    HistoricalPendingCoachReset,
    HistoricalRecordedSplit,
    HistoricalSessionState,
    HistoricalStopPauseInterval,
    HistoricalVerifiedSplit,
    ReplayResult,
)
from swimcore.replay.validation import validate_event_stream

__all__ = [
    "EmptyReplayError",
    "HistoricalControlDecision",
    "HistoricalPendingCoachReset",
    "HistoricalRecordedSplit",
    "HistoricalSessionState",
    "HistoricalStopPauseInterval",
    "HistoricalVerifiedSplit",
    "ReplayCommandBatchError",
    "ReplayDuplicateEventIdError",
    "ReplayDurationError",
    "ReplayError",
    "ReplayResult",
    "ReplaySequenceError",
    "ReplaySessionMismatchError",
    "ReplaySplitError",
    "ReplayStopPauseError",
    "ReplayTimestampError",
    "ReplayTransitionError",
    "UnsupportedReplaySchemaError",
    "replay_session",
    "validate_event_stream",
]
