"""StopPause and lifecycle-pause analytics (separate axes by design)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from contracts.enums import EventType
from contracts.events import (
    EventEnvelope,
    SessionPausedPayload,
    SessionResumedPayload,
    SplitRecordedPayload,
    StopPauseResolvedPayload,
    StopPauseStartedPayload,
)
from contracts.session_report import (
    MetricStatus,
    StopPauseAnalysis,
    StopPauseIntervalSummary,
)
from swimcore.replay.state import HistoricalSessionState


@dataclass(frozen=True, slots=True)
class TimeInterval:
    startMs: int
    endMs: int


def lifecycle_pause_intervals(
    events: Sequence[EventEnvelope], horizon_ms: int
) -> tuple[TimeInterval, ...]:
    intervals: list[TimeInterval] = []
    opened: int | None = None
    for event in events:
        if event.type is EventType.SessionPaused:
            payload = event.payload
            assert isinstance(payload, SessionPausedPayload)
            opened = payload.atMs
        elif event.type is EventType.SessionResumed:
            payload = event.payload
            assert isinstance(payload, SessionResumedPayload)
            if opened is not None:
                intervals.append(TimeInterval(opened, payload.atMs))
                opened = None
    if opened is not None:
        intervals.append(TimeInterval(opened, horizon_ms))
    return tuple(intervals)


def _official_distance_at_or_before(
    state: HistoricalSessionState, timestamp_ms: int
) -> float | None:
    distance: float | None = 0.0 if state.poolLengthM is not None else None
    for split in state.recordedSplits:
        if split.wallTimestampMs <= timestamp_ms:
            distance = split.officialDistanceM
        else:
            break
    return distance


def _reconciled_wall_distance(
    *,
    events: Sequence[EventEnvelope],
    resolved_seq: int | None,
    pool_length_m: int | None,
) -> float | None:
    if resolved_seq is None or pool_length_m is None:
        return None
    for event in events:
        if event.seq <= resolved_seq or event.type is not EventType.SplitRecorded:
            continue
        payload = event.payload
        assert isinstance(payload, SplitRecordedPayload)
        return float((payload.lengthIndex + 1) * pool_length_m)
    return None


def build_stop_pause_analysis(
    replay_state: HistoricalSessionState,
    events: Sequence[EventEnvelope],
) -> StopPauseAnalysis:
    started: dict[str, tuple[StopPauseStartedPayload, int]] = {}
    resolved_seq: dict[str, int] = {}
    for event in events:
        if event.type is EventType.StopPauseStarted:
            payload = event.payload
            assert isinstance(payload, StopPauseStartedPayload)
            started[payload.intervalId] = (payload, event.tsMs)
        elif event.type is EventType.StopPauseResolved:
            payload = event.payload
            assert isinstance(payload, StopPauseResolvedPayload)
            resolved_seq[payload.intervalId] = event.seq

    interval_summaries: list[StopPauseIntervalSummary] = []
    ordered = list(replay_state.completedStopPauses)
    if replay_state.openStopPause is not None:
        ordered.append(replay_state.openStopPause)

    manual = 0
    automatic = 0
    temporary = 0
    reconciled = 0
    pending_reconciliation = 0
    retroactive = 0
    durations: list[int] = []
    for index, historical in enumerate(ordered):
        start_payload, confirmed_at = started.get(historical.intervalId, (None, None))
        alignment_source = (
            start_payload.alignmentSource.value if start_payload is not None else None
        )
        alignment_quality = (
            start_payload.alignmentQuality.value if start_payload is not None else None
        )
        start_quality = (
            start_payload.stopStartTimeQuality.value if start_payload is not None else None
        )
        if historical.detectionSource == "COACH":
            manual += 1
        else:
            automatic += 1
        pending_at_resolve = historical.wallReconciliationPendingAtResolve
        if start_payload is not None and start_payload.wallReconciliationPending:
            temporary += 1
        reconciled_wall_m = (
            _reconciled_wall_distance(
                events=events,
                resolved_seq=resolved_seq.get(historical.intervalId),
                pool_length_m=replay_state.poolLengthM,
            )
            if pending_at_resolve
            else None
        )
        reconciliation_completed = reconciled_wall_m is not None
        reconciliation_pending_at_report = pending_at_resolve and not reconciliation_completed
        if reconciliation_completed:
            reconciled += 1
        if reconciliation_pending_at_report:
            pending_reconciliation += 1
        freeze_ms = max(0, (confirmed_at or historical.startedAtMs) - historical.startedAtMs)
        if freeze_ms > 0:
            retroactive += 1
        if historical.durationMs is not None:
            durations.append(historical.durationMs)
        official_after = _official_distance_at_or_before(
            replay_state,
            historical.endedAtMs or replay_state.lastEventTimestampMs,
        )
        interval_summaries.append(
            StopPauseIntervalSummary(
                stopIndex=index,
                intervalId=historical.intervalId,
                trigger=historical.trigger,
                startedAtMs=historical.startedAtMs,
                confirmedAtMs=confirmed_at,
                resolvedAtMs=historical.endedAtMs,
                durationMs=historical.durationMs,
                alignmentSource=alignment_source,
                estimatedAlignmentDistanceM=None,
                officialDistanceBeforeM=_official_distance_at_or_before(
                    replay_state, historical.startedAtMs
                ),
                officialDistanceAfterM=official_after,
                reconciledAtWallM=reconciled_wall_m,
                retroactiveFreezeMs=freeze_ms,
                detectionSource=historical.detectionSource,
                stopStartTimeQuality=start_quality,
                alignmentQuality=alignment_quality,
                resolved=historical.endedAtMs is not None,
                wallReconciliationPendingAtResolve=pending_at_resolve,
                wallReconciliationCompleted=reconciliation_completed,
                wallReconciliationPendingAtReport=reconciliation_pending_at_report,
            )
        )

    count = len(ordered)
    total = replay_state.stoppedDurationMs
    longest = max(durations, default=0)
    mean_duration = total / count if count else None
    resolved_count = len(replay_state.completedStopPauses)
    unresolved_count = 1 if replay_state.openStopPause is not None else 0
    return StopPauseAnalysis(
        status=MetricStatus.AVAILABLE,
        stopPauseCount=count,
        totalStoppedDurationMs=total,
        longestStopDurationMs=longest,
        meanStopDurationMs=mean_duration,
        resolvedStopCount=resolved_count,
        unresolvedStopCount=unresolved_count,
        retroactiveStopCount=retroactive,
        manualStopCount=manual,
        automaticStopCount=automatic,
        temporaryAlignmentCount=temporary,
        wallReconciliationCount=reconciled,
        pendingWallReconciliationCount=pending_reconciliation,
        intervals=tuple(interval_summaries),
    )


def stop_pause_intervals(
    state: HistoricalSessionState, horizon_ms: int
) -> tuple[TimeInterval, ...]:
    intervals = [
        TimeInterval(item.startedAtMs, item.endedAtMs)
        for item in state.completedStopPauses
        if item.endedAtMs is not None
    ]
    if state.openStopPause is not None:
        intervals.append(TimeInterval(state.openStopPause.startedAtMs, horizon_ms))
    return tuple(intervals)
