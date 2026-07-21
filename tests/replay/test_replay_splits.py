"""Replay split/verification reconstruction tests (Commit 7 §16, §20, ADR-036)."""

from __future__ import annotations

import pytest

from contracts.enums import SplitSource, VerificationSource
from swimcore.replay import ReplaySplitError, replay_session
from tests.replay._stream_helpers import POOL, StreamBuilder

pytestmark = pytest.mark.replay


def test_split_reconstruction() -> None:
    b = StreamBuilder().running(0)
    for i, ts in enumerate((20_000, 40_000, 60_000)):
        b.split(i, ts)
    state = replay_session(b.events).state
    assert state.officialCompletedLengthCount == 3
    assert state.officialCompletedDistanceM == 3 * POOL
    assert [s.splitId for s in state.recordedSplits] == ["split-0", "split-1", "split-2"]
    assert [s.wallTimestampMs for s in state.recordedSplits] == [20_000, 40_000, 60_000]
    assert [s.officialDistanceM for s in state.recordedSplits] == [25.0, 50.0, 75.0]


def test_verification_reconstruction() -> None:
    b = StreamBuilder().running(0).split(0, 20_000).verified(0, 21_000)
    state = replay_session(b.events).state
    assert len(state.verifiedSplits) == 1
    v = state.verifiedSplits[0]
    assert v.splitId == "split-0"
    assert v.verificationSource == VerificationSource.SECOND_TIMER.value
    assert v.verifiedWallTimestampMs == 21_000


def test_duplicate_split_id_rejected() -> None:
    b = StreamBuilder().running(0).split(0, 20_000).split(1, 40_000, split_id="split-0")
    with pytest.raises(ReplaySplitError, match="already recorded"):
        replay_session(b.events)


def test_out_of_order_length_index_rejected() -> None:
    b = StreamBuilder().running(0).split(1, 20_000)
    with pytest.raises(ReplaySplitError, match="out of order"):
        replay_session(b.events)


def test_non_monotonic_split_wall_time_rejected() -> None:
    b = StreamBuilder().running(0)
    b.split(0, 40_000)
    # envelope ts must not decrease either, so keep envelope ts equal but payload earlier
    from contracts.enums import EventType, SplitQualityFlag
    from contracts.events import SplitRecordedPayload

    b.add(
        EventType.SplitRecorded,
        SplitRecordedPayload(
            sessionId=b.session_id,
            splitId="split-1",
            lengthIndex=1,
            wallTimestampMs=30_000,  # earlier than split-0's wall time
            source=SplitSource.TOUCHPAD,
            qualityFlag=SplitQualityFlag.MANUAL_UNVERIFIED,
        ),
        40_000,
    )
    with pytest.raises(ReplaySplitError, match="monotonic"):
        replay_session(b.events)


def test_verification_before_recording_rejected() -> None:
    b = StreamBuilder().running(0).verified(0, 21_000)
    with pytest.raises(ReplaySplitError, match="before SplitRecorded"):
        replay_session(b.events)


def test_conflicting_second_verification_rejected() -> None:
    b = StreamBuilder().running(0).split(0, 20_000)
    b.verified(0, 21_000)
    b.verified(0, 25_000, source=VerificationSource.VIDEO)  # different content
    with pytest.raises(ReplaySplitError, match="conflicting"):
        replay_session(b.events)


def test_identical_reverification_is_idempotent() -> None:
    b = StreamBuilder().running(0).split(0, 20_000)
    b.verified(0, 21_000)
    b.verified(0, 21_000)
    state = replay_session(b.events).state
    assert len(state.verifiedSplits) == 1


def test_official_distance_from_wall_geometry() -> None:
    b = StreamBuilder().running(0).split(0, 20_000)
    state = replay_session(b.events).state
    assert state.recordedSplits[0].officialDistanceM == float(POOL)
    assert state.officialCompletedDistanceM == float(POOL)


def test_wearable_estimate_never_rewrites_official_distance() -> None:
    """A WEARABLE-sourced split still gets pool-geometry distance (ADR-036).

    The event payload deliberately carries NO estimated metres field; official distance is
    always ``(lengthIndex + 1) * poolLengthM`` — a 50 m swim can never be reported 45 m.
    """
    b = StreamBuilder().running(0)
    b.split(0, 20_000, source=SplitSource.WEARABLE)
    b.split(1, 40_000, source=SplitSource.WEARABLE)
    state = replay_session(b.events).state
    assert [s.officialDistanceM for s in state.recordedSplits] == [25.0, 50.0]
    assert state.officialCompletedDistanceM == 50.0
    assert state.recordedSplits[0].source == SplitSource.WEARABLE.value


def test_official_distance_is_none_when_pool_unknown() -> None:
    b = StreamBuilder().created(0, pool=None).armed(0).started(0).split(0, 20_000)
    state = replay_session(b.events).state
    assert state.recordedSplits[0].officialDistanceM is None
    assert state.officialCompletedDistanceM is None
    assert state.officialCompletedLengthCount == 1
