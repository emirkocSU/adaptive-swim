"""Deterministic virtual swimmer models for the headless simulator (Commit 8).

A virtual swimmer converts an approved plan (the ghost target) plus a scenario's behavioural
profile into a concrete sequence of wall-touch timestamps and, where relevant, an externally
tracked mid-pool alignment point for a StopPause. It is a *test double for a human*, kept in
the simulator package only — it is never imported by ``swimcore``, ``contracts`` or
``persistence``.

Determinism: any randomness is drawn from an explicit integer seed via a small splitmix64
PRNG, so a given (scenario, seed) always yields identical output. No ``random`` module, no
system clock, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class _SplitMix64:
    """Tiny deterministic PRNG (splitmix64). Seeded explicitly; no global state."""

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        self._state = seed & 0xFFFFFFFFFFFFFFFF

    def next_u64(self) -> int:
        self._state = (self._state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self._state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def uniform(self, lo: float, hi: float) -> float:
        """Deterministic float in [lo, hi)."""
        frac = self.next_u64() / 2.0**64
        return lo + (hi - lo) * frac


@dataclass(frozen=True, slots=True)
class WallTouch:
    """One official wall touch produced by the virtual swimmer."""

    lengthIndex: int
    distanceM: float
    wallTimestampMs: int


@dataclass(frozen=True, slots=True)
class SwimmerStopEvent:
    """An externally observed StopPause the virtual swimmer performs (never estimated)."""

    stopStartedAtMs: int
    confirmedAtMs: int
    resumedAtMs: int
    trackedAlignmentDistanceM: float


@dataclass(frozen=True, slots=True)
class VirtualSwimResult:
    """Full deterministic output of a virtual swim over one plan."""

    wallTouches: tuple[WallTouch, ...]
    stopEvent: SwimmerStopEvent | None = field(default=None)


@dataclass(frozen=True, slots=True)
class SwimmerBehaviour:
    """Behavioural knobs for a scenario (all deterministic).

    ``paceBiasFactor`` scales each length's target duration (1.0 = exactly on the ghost
    plan, >1 slower, <1 faster). ``jitterFractionPerLength`` is the half-width of a
    deterministic uniform per-length timing jitter, as a fraction of that length's target
    duration. ``fadeFactorPerLength`` compounds a slow-down each length (1.0 = none).
    """

    paceBiasFactor: float = 1.0
    jitterFractionPerLength: float = 0.0
    fadeFactorPerLength: float = 1.0


def swim_walls(
    *,
    pool_length_m: int,
    total_distance_m: float,
    target_time_at_wall_ms: list[int],
    behaviour: SwimmerBehaviour,
    seed: int,
    start_offset_ms: int = 0,
) -> tuple[WallTouch, ...]:
    """Produce deterministic wall touches from the ghost's per-wall target times.

    ``target_time_at_wall_ms[i]`` is the ghost's active-time target (ms) at wall ``i+1``.
    The swimmer's actual per-length duration = ghost length duration × bias × fade^i, plus a
    deterministic seeded jitter. Wall timestamps are wall-clock (start offset + cumulative).
    """
    rng = _SplitMix64(seed)
    touches: list[WallTouch] = []
    prev_target = 0
    cumulative = start_offset_ms
    fade = 1.0
    for i, target_ms in enumerate(target_time_at_wall_ms):
        ghost_len_ms = target_ms - prev_target
        prev_target = target_ms
        length_ms = ghost_len_ms * behaviour.paceBiasFactor * fade
        if behaviour.jitterFractionPerLength > 0.0:
            half = length_ms * behaviour.jitterFractionPerLength
            length_ms += rng.uniform(-half, half)
        fade *= behaviour.fadeFactorPerLength
        cumulative += int(round(max(length_ms, 1.0)))
        distance = min(float((i + 1) * pool_length_m), total_distance_m)
        touches.append(WallTouch(lengthIndex=i, distanceM=distance, wallTimestampMs=cumulative))
    return tuple(touches)
