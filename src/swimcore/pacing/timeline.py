"""Timeline compilation and active-time <-> ghost-distance queries.

The timeline carries **active swimming time only**. Rest is excluded; StopPause and real
elapsed time are runtime concerns for a later commit. The compiler expands every repeat
block into concrete repetitions and resolves each segment into a linear pace interval in
global distance coordinates.
"""

from __future__ import annotations

import math

from contracts.workout import PaceSegment, WorkoutTemplateVersion
from swimcore.pacing.curves import (
    curve_duration,
    elapsed_at_local_distance,
    local_distance_at_elapsed,
    pace_at_local_distance,
    resolve_curve_endpoints,
)
from swimcore.pacing.errors import (
    DistanceOutsideTimelineError,
    InvalidDistanceError,
    InvalidDurationError,
    InvalidPaceCurveError,
    InvalidPoolLengthError,
    TimeOutsideTimelineError,
)
from swimcore.pacing.math import _finite
from swimcore.pacing.types import (
    EPSILON,
    DistanceAtTimeResult,
    PaceInterval,
    PaceTimeline,
    TimeAtDistanceResult,
)


def _interval_from_segment(seg: PaceSegment, offset_m: float) -> PaceInterval:
    length = seg.toM - seg.fromM
    p0, p1 = resolve_curve_endpoints(
        seg.mode.value, seg.targetPaceSecPer100M, seg.startPaceSecPer100M, seg.endPaceSecPer100M
    )
    return PaceInterval(
        fromM=offset_m,
        toM=offset_m + length,
        startPaceSecPer100M=p0,
        endPaceSecPer100M=p1,
        mode=seg.mode.value,
        activeDurationSec=curve_duration(length, p0, p1),
    )


def _terminal_pace(seg: PaceSegment) -> float:
    if seg.mode.value == "progressive" and seg.endPaceSecPer100M is not None:
        return seg.endPaceSecPer100M
    return seg.targetPaceSecPer100M


def _assert_compilable(workout: WorkoutTemplateVersion) -> None:
    """Reject a semantically-invalid workout before compiling a pace timeline.

    Covers the pace-relevant defects: coverage (gap/overlap/reversed), controlled-start /
    progressive direction+presence (via ``resolve_curve_endpoints``), negative-split
    ordering, and target pace conflicting with adaptation bounds. This is the minimum the
    pacing layer must guarantee for itself; it is not a copy of the full semantic validator.
    """
    for b, block in enumerate(workout.blocks):
        segs = block.segments
        if abs(segs[0].fromM) > EPSILON:
            raise InvalidPaceCurveError(f"block {b}: first segment must start at 0")
        for s, seg in enumerate(segs):
            if seg.toM <= seg.fromM + EPSILON:
                raise InvalidPaceCurveError(f"block {b} segment {s}: reversed/zero-length")
            # direction + presence for controlled_start / progressive
            resolve_curve_endpoints(
                seg.mode.value,
                seg.targetPaceSecPer100M,
                seg.startPaceSecPer100M,
                seg.endPaceSecPer100M,
            )
        for s in range(len(segs) - 1):
            if segs[s + 1].fromM > segs[s].toM + EPSILON:
                raise InvalidPaceCurveError(f"block {b}: gap before segment {s + 1}")
            if segs[s + 1].fromM < segs[s].toM - EPSILON:
                raise InvalidPaceCurveError(f"block {b}: overlap at segment {s + 1}")
        if abs(segs[-1].toM - block.distanceM) > EPSILON:
            raise InvalidPaceCurveError(f"block {b}: last segment must end at block distance")

        prev_terminal: float | None = None
        for s, seg in enumerate(segs):
            if (
                seg.mode.value == "negative_split_part"
                and prev_terminal is not None
                and seg.targetPaceSecPer100M > prev_terminal + EPSILON
            ):
                raise InvalidPaceCurveError(
                    f"block {b} segment {s}: negative-split part slower than previous terminal"
                )
            prev_terminal = _terminal_pace(seg)

        adaptation = block.adaptation
        if adaptation is not None and adaptation.mode.value != "off":
            fastest = adaptation.fastestAllowedPaceSecPer100M
            slowest = adaptation.slowestAllowedPaceSecPer100M
            for s, seg in enumerate(segs):
                if fastest is not None and seg.targetPaceSecPer100M < fastest - EPSILON:
                    raise InvalidPaceCurveError(
                        f"block {b} segment {s}: target faster than adaptation fastest bound"
                    )
                if slowest is not None and seg.targetPaceSecPer100M > slowest + EPSILON:
                    raise InvalidPaceCurveError(
                        f"block {b} segment {s}: target slower than adaptation slowest bound"
                    )


def compile_pace_timeline(workout: WorkoutTemplateVersion) -> PaceTimeline:
    """Expand blocks × repetitions into a global active-time pace timeline (rest excluded).

    Raises ``PaceMathError`` (``InvalidPaceCurveError``) for a semantically-invalid workout
    rather than silently producing a wrong timeline.
    """
    _assert_compilable(workout)
    intervals: list[PaceInterval] = []
    offset = 0.0
    total_active = 0.0
    for block in workout.blocks:
        for _ in range(block.repetitions):
            for seg in block.segments:
                interval = _interval_from_segment(seg, offset)
                intervals.append(interval)
                offset = interval.toM
                total_active += interval.activeDurationSec
    return PaceTimeline(
        totalDistanceM=offset,
        totalActiveDurationSec=total_active,
        intervals=tuple(intervals),
    )


def target_active_time_at_distance(
    timeline: PaceTimeline,
    distance_m: float,
) -> TimeAtDistanceResult:
    """Active swim time the ghost target takes to reach ``distance_m``."""
    if not _finite(distance_m):
        raise InvalidDistanceError(f"distance must be finite, got {distance_m}")
    if distance_m < -EPSILON:
        raise InvalidDistanceError(f"distance must be >= 0, got {distance_m}")
    if distance_m > timeline.totalDistanceM + EPSILON:
        raise DistanceOutsideTimelineError(
            f"distance {distance_m} exceeds total {timeline.totalDistanceM}"
        )
    distance_m = min(max(distance_m, 0.0), timeline.totalDistanceM)
    if distance_m <= EPSILON:
        first_pace = timeline.intervals[0].startPaceSecPer100M if timeline.intervals else 0.0
        return TimeAtDistanceResult(distanceM=0.0, elapsedActiveSec=0.0, paceSecPer100M=first_pace)

    elapsed = 0.0
    for interval in timeline.intervals:
        length = interval.lengthM
        if distance_m >= interval.toM - EPSILON:
            elapsed += interval.activeDurationSec
            continue
        x = distance_m - interval.fromM
        elapsed += elapsed_at_local_distance(
            x, length, interval.startPaceSecPer100M, interval.endPaceSecPer100M
        )
        pace = pace_at_local_distance(
            x, length, interval.startPaceSecPer100M, interval.endPaceSecPer100M
        )
        return TimeAtDistanceResult(
            distanceM=distance_m, elapsedActiveSec=elapsed, paceSecPer100M=pace
        )
    # exactly total distance
    last = timeline.intervals[-1]
    return TimeAtDistanceResult(
        distanceM=distance_m,
        elapsedActiveSec=timeline.totalActiveDurationSec,
        paceSecPer100M=last.endPaceSecPer100M,
    )


def ghost_distance_at_active_time(
    timeline: PaceTimeline,
    elapsed_active_sec: float,
    clamp: bool = False,
) -> DistanceAtTimeResult:
    """Ghost distance reached after ``elapsed_active_sec`` of active swimming."""
    if not _finite(elapsed_active_sec):
        raise InvalidDurationError(f"active time must be finite, got {elapsed_active_sec}")
    if elapsed_active_sec < -EPSILON:
        raise InvalidDurationError(f"active time must be >= 0, got {elapsed_active_sec}")
    if elapsed_active_sec > timeline.totalActiveDurationSec + EPSILON:
        if clamp:
            last_pace = timeline.intervals[-1].endPaceSecPer100M if timeline.intervals else 0.0
            return DistanceAtTimeResult(
                elapsedActiveSec=elapsed_active_sec,
                distanceM=timeline.totalDistanceM,
                paceSecPer100M=last_pace,
                clamped=True,
            )
        raise TimeOutsideTimelineError(
            f"active time {elapsed_active_sec} exceeds total {timeline.totalActiveDurationSec}"
        )
    if elapsed_active_sec <= EPSILON:
        first_pace = timeline.intervals[0].startPaceSecPer100M if timeline.intervals else 0.0
        return DistanceAtTimeResult(elapsedActiveSec=0.0, distanceM=0.0, paceSecPer100M=first_pace)

    cumulative = 0.0
    for interval in timeline.intervals:
        if elapsed_active_sec >= cumulative + interval.activeDurationSec - EPSILON:
            cumulative += interval.activeDurationSec
            continue
        t_local = elapsed_active_sec - cumulative
        x = local_distance_at_elapsed(
            t_local, interval.lengthM, interval.startPaceSecPer100M, interval.endPaceSecPer100M
        )
        pace = pace_at_local_distance(
            x, interval.lengthM, interval.startPaceSecPer100M, interval.endPaceSecPer100M
        )
        return DistanceAtTimeResult(
            elapsedActiveSec=elapsed_active_sec,
            distanceM=interval.fromM + x,
            paceSecPer100M=pace,
        )
    last = timeline.intervals[-1]
    return DistanceAtTimeResult(
        elapsedActiveSec=elapsed_active_sec,
        distanceM=timeline.totalDistanceM,
        paceSecPer100M=last.endPaceSecPer100M,
    )


# --------------------------------------------------------------------------- wall helpers
def _validate_pool(pool_length_m: int) -> None:
    if not _finite(pool_length_m):
        raise InvalidPoolLengthError(f"pool length must be finite, got {pool_length_m}")
    if pool_length_m <= 0:
        raise InvalidPoolLengthError(f"pool length must be > 0, got {pool_length_m}")


def _validate_finite_distance(distance_m: float, label: str = "distance") -> None:
    if not _finite(distance_m):
        raise InvalidDistanceError(f"{label} must be finite, got {distance_m}")
    if distance_m < -EPSILON:
        raise InvalidDistanceError(f"{label} must be >= 0, got {distance_m}")


def is_wall_boundary(distance_m: float, pool_length_m: int) -> bool:
    _validate_pool(pool_length_m)
    _validate_finite_distance(distance_m)
    ratio = distance_m / pool_length_m
    return abs(ratio - round(ratio)) < 1e-6


def previous_wall_boundary(distance_m: float, pool_length_m: int) -> float:
    _validate_pool(pool_length_m)
    _validate_finite_distance(distance_m)
    k = math.floor(distance_m / pool_length_m + 1e-6)
    return float(k * pool_length_m)


def next_wall_boundary(
    distance_m: float,
    pool_length_m: int,
    total_distance_m: float,
) -> float:
    _validate_pool(pool_length_m)
    _validate_finite_distance(distance_m)
    _validate_finite_distance(total_distance_m, "total distance")
    if distance_m > total_distance_m + EPSILON:
        raise InvalidDistanceError(
            f"distance {distance_m} exceeds total distance {total_distance_m}"
        )
    k = math.floor(distance_m / pool_length_m + 1e-6)
    candidate = float((k + 1) * pool_length_m)
    if candidate > total_distance_m + EPSILON:
        # The next wall would exceed the timeline. Only clamp to the total if the total is
        # itself a valid wall; otherwise there is no valid wall at/after this distance.
        if is_wall_boundary(total_distance_m, pool_length_m):
            return max(total_distance_m, distance_m)
        raise InvalidDistanceError(
            f"no wall boundary between {distance_m} and total {total_distance_m} "
            f"(pool {pool_length_m}); total is not a wall"
        )
    # never step backward relative to the current position
    return max(candidate, distance_m)
