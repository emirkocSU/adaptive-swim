"""Split identity: splitId is distinct from lengthIndex (§2.3)."""

from __future__ import annotations

import pytest

from contracts.commands import RecordSplit, VerifySplit
from swimcore.session import SplitVerificationConflictError
from tests.unit._session_helpers import record_split, started


def test_split_id_is_required_and_distinct_from_length_index() -> None:
    agg, _ = started()
    agg.handle(record_split(agg, 0))
    # internal maps key by splitId and by lengthIndex separately
    assert agg.splitIdByLengthIndex[0] == "split-0"
    assert "split-0" in agg.recordedSplitsById


def test_duplicate_split_id_same_content_is_idempotent() -> None:
    agg, _ = started()
    cmd = record_split(agg, 0)
    agg.handle(cmd)
    again = agg.handle(cmd)
    assert again  # same events returned, no conflict
    assert len(agg.recordedSplits) == 1


def test_duplicate_length_index_is_conflict() -> None:
    agg, _ = started()
    agg.handle(record_split(agg, 0))
    with pytest.raises(SplitVerificationConflictError):
        agg.handle(
            RecordSplit(
                clientCommandId="other",
                sessionId=agg.sessionId,
                splitId="split-other",
                lengthIndex=0,
                wallTimestampMs=41000,
                source="TOUCHPAD",
                distanceM=25.0,
            )
        )


def test_verification_uses_split_id() -> None:
    agg, _ = started()
    agg.handle(record_split(agg, 0))
    events = agg.handle(
        VerifySplit(
            clientCommandId="v0",
            sessionId=agg.sessionId,
            splitId="split-0",
            lengthIndex=0,
            verificationSource="SECOND_TIMER",
            verifiedWallTimestampMs=40000,
        )
    )
    assert events[0].payload.splitId == "split-0"


def test_verification_wrong_split_id_for_length_is_conflict() -> None:
    agg, _ = started()
    agg.handle(record_split(agg, 0))
    with pytest.raises(SplitVerificationConflictError):
        agg.handle(
            VerifySplit(
                clientCommandId="vx",
                sessionId=agg.sessionId,
                splitId="split-0",
                lengthIndex=1,
                verificationSource="SECOND_TIMER",
                verifiedWallTimestampMs=40000,
            )
        )
