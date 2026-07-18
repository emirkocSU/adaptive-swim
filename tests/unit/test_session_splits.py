"""Commit 6 — split recording and verification (splitId + wall-bound)."""

from __future__ import annotations

import pytest

from contracts.commands import RecordSplit, VerifySplit
from swimcore.session import (
    CommandIdConflictError,
    SplitNotFoundError,
    SplitVerificationConflictError,
)
from swimcore.session.errors import InvalidSplitBoundaryError
from tests.unit._session_helpers import record_split, started


def test_record_valid_wall_split() -> None:
    agg, clk = started()
    ev = agg.handle(record_split(agg, 0))
    assert ev[-1].type.value == "SplitRecorded"
    assert 0 in agg.recordedSplits


def test_split_requires_distance() -> None:
    agg, clk = started()
    with pytest.raises(InvalidSplitBoundaryError):
        agg.handle(
            RecordSplit(
                clientCommandId="s",
                sessionId=agg.sessionId,
                splitId="x",
                lengthIndex=0,
                wallTimestampMs=40000,
                source="TOUCHPAD",
                distanceM=None,
            )
        )


def test_non_wall_split_is_rejected() -> None:
    agg, clk = started()
    with pytest.raises(InvalidSplitBoundaryError):
        agg.handle(
            RecordSplit(
                clientCommandId="s",
                sessionId=agg.sessionId,
                splitId="x",
                lengthIndex=0,
                wallTimestampMs=40000,
                source="TOUCHPAD",
                distanceM=13.0,
            )
        )


def test_split_distance_must_match_length_index() -> None:
    agg, clk = started()
    with pytest.raises(InvalidSplitBoundaryError):
        agg.handle(
            RecordSplit(
                clientCommandId="s",
                sessionId=agg.sessionId,
                splitId="x",
                lengthIndex=0,
                wallTimestampMs=40000,
                source="TOUCHPAD",
                distanceM=50.0,
            )
        )  # length 0 must be 25


def test_split_id_is_required_and_distinct_from_length_index() -> None:
    agg, clk = started()
    agg.handle(record_split(agg, 0))
    assert agg.splitIdByLengthIndex[0] == "split-0"


def test_duplicate_split_id_same_content_is_idempotent() -> None:
    agg, clk = started()
    e1 = agg.handle(record_split(agg, 0, cid="s0"))
    e2 = agg.handle(record_split(agg, 0, cid="s0"))
    assert [e.eventId for e in e1] == [e.eventId for e in e2]
    assert len(agg.recordedSplits) == 1


def test_duplicate_split_id_different_content_is_conflict() -> None:
    agg, clk = started()
    agg.handle(record_split(agg, 0, cid="s0"))
    with pytest.raises(CommandIdConflictError):
        # same clientCommandId, different content
        agg.handle(
            RecordSplit(
                clientCommandId="s0",
                sessionId=agg.sessionId,
                splitId="split-0",
                lengthIndex=0,
                wallTimestampMs=41000,
                source="TOUCHPAD",
                distanceM=25.0,
            )
        )


def test_reject_second_split_same_length() -> None:
    agg, clk = started()
    agg.handle(record_split(agg, 0, cid="s0"))
    with pytest.raises(SplitVerificationConflictError):
        agg.handle(
            RecordSplit(
                clientCommandId="s0b",
                sessionId=agg.sessionId,
                splitId="other",
                lengthIndex=0,
                wallTimestampMs=42000,
                source="TOUCHPAD",
                distanceM=25.0,
            )
        )


def test_verify_existing_split_uses_split_id() -> None:
    agg, clk = started()
    agg.handle(record_split(agg, 0))
    ev = agg.handle(
        VerifySplit(
            clientCommandId="v0",
            sessionId=agg.sessionId,
            splitId="split-0",
            lengthIndex=0,
            verificationSource="VIDEO",
            verifiedWallTimestampMs=40010,
        )
    )
    assert ev[-1].type.value == "SplitVerified"


def test_reject_verification_for_missing_split() -> None:
    agg, clk = started()
    with pytest.raises(SplitNotFoundError):
        agg.handle(
            VerifySplit(
                clientCommandId="v0",
                sessionId=agg.sessionId,
                splitId="nope",
                lengthIndex=0,
                verificationSource="VIDEO",
                verifiedWallTimestampMs=40010,
            )
        )


def test_conflicting_verification_rejected() -> None:
    agg, clk = started()
    agg.handle(record_split(agg, 0))
    agg.handle(
        VerifySplit(
            clientCommandId="v0",
            sessionId=agg.sessionId,
            splitId="split-0",
            lengthIndex=0,
            verificationSource="VIDEO",
            verifiedWallTimestampMs=40010,
        )
    )
    with pytest.raises(SplitVerificationConflictError):
        agg.handle(
            VerifySplit(
                clientCommandId="v1",
                sessionId=agg.sessionId,
                splitId="split-0",
                lengthIndex=0,
                verificationSource="SECOND_TIMER",
                verifiedWallTimestampMs=40999,
            )
        )


def test_stop_pause_does_not_mark_split_invalid() -> None:
    from contracts.commands import MarkStopPause, ResolveStopPause

    agg, clk = started()
    agg.handle(
        MarkStopPause(
            clientCommandId="st",
            sessionId=agg.sessionId,
            trigger="COACH_STOP",
            stopStartedAtMs=10000,
            confirmedAtMs=20000,
            detectionSource="COACH",
            trackedAlignmentDistanceM=23.0,
        )
    )  # expected wall 25 = length 0
    iid = agg.processedClientCommandIds["st"][1][-1].payload.intervalId
    agg.handle(
        ResolveStopPause(
            clientCommandId="r", sessionId=agg.sessionId, intervalId=iid, resumedAtMs=20000
        )
    )
    agg.handle(record_split(agg, 0, ts=25000))  # reconciles + records
    assert agg.recordedSplits[0].qualityFlag != "INVALID"
