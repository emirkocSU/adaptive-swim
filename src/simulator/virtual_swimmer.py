"""Deterministic virtual swimmer for the headless simulator (Commit 8, corrected).

The virtual swimmer is a *tick-based* deterministic simulation of a human following the
ghost plan (§2.3). Every tick produces an immutable :class:`SwimmerObservation`; official
wall crossings are found by deterministic interpolation inside the tick that crosses the
wall. The swimmer:

- never produces the target plan itself and never copies PCHIP / compiler math — target
  position and speed come from real ``swimcore`` timeline queries supplied by the harness;
- draws all randomness from an instance-local splitmix64 PRNG seeded explicitly (no global
  ``random.seed()``, no wall clock, no I/O, and never sleeps);
- models actual motion as ``target envelope × deterministic response + fatigue trend +
  seeded bounded gaussian noise + scenario injection`` (stops, planned rest, turn delay);
- reports an *estimated* position in observations only — the estimate is never the
  official distance (official distance comes from wall touches / pool geometry).

The legacy wall-touch generator (``swim_walls``) is retained for the old demo scenarios;
the eight required acceptance scenarios all run through :func:`simulate_swim`.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

#: Version stamp of the virtual swimmer model (bump on behavioural changes).
VIRTUAL_SWIMMER_VERSION = "virtual-swimmer-2.0.0"


class _SplitMix64:
    """Tiny deterministic PRNG (splitmix64). Instance-local; seeded explicitly."""

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

    def gauss(self, mu: float, sigma: float) -> float:
        """Deterministic gaussian via Box–Muller (uses two uniform draws)."""
        if sigma <= 0.0:
            return mu
        u1 = max(self.next_u64() / 2.0**64, 1e-18)
        u2 = self.next_u64() / 2.0**64
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


# --------------------------------------------------------------------------- legacy wall model
@dataclass(frozen=True, slots=True)
class WallTouch:
    """One official wall touch produced by the virtual swimmer."""

    lengthIndex: int
    distanceM: float
    wallTimestampMs: int


@dataclass(frozen=True, slots=True)
class SwimmerBehaviour:
    """Behavioural knobs for the legacy demo wall model (all deterministic)."""

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
    """Legacy per-length wall-touch generator (demo scenarios only)."""
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


# --------------------------------------------------------------------------- tick model (§2.3)
@dataclass(frozen=True, slots=True)
class VirtualSwimmerConfig:
    """Deterministic tick-simulation configuration (§2.3)."""

    seed: int
    tickMs: int = 100
    #: actual speed = target speed × baseResponseRatio (before fatigue/noise). <1 = slower.
    baseResponseRatio: float = 1.0
    #: fractional slowdown accumulated per 100 m swum (0 = none).
    fatigueSlopePer100M: float = 0.0
    #: std-dev of the per-tick gaussian speed noise (m/s).
    noiseStdMps: float = 0.0
    minimumActualSpeedMps: float = 0.05
    maximumActualSpeedMps: float = 3.5
    #: dwell at each wall before the next length starts (turn), ms.
    turnDelayMs: int = 0


@dataclass(frozen=True, slots=True)
class SwimmerObservation:
    """One immutable per-tick observation (§2.3). Estimated position is VISUAL ONLY."""

    wallTimeMs: int
    activeTimeMs: int
    actualDistanceM: float
    actualSpeedMps: float
    targetDistanceM: float
    targetSpeedMps: float
    gapM: float
    phaseType: str
    positionQuality: str
    plannedRest: bool


@dataclass(frozen=True, slots=True)
class RestWindow:
    """Planned rest modeled at the simulator SCHEDULE level (never a StopPause)."""

    afterLengthIndex: int
    durationMs: int


@dataclass(frozen=True, slots=True)
class StopWindow:
    """An unplanned full stop anchored after a wall (drives a StopPause scenario)."""

    afterLengthIndex: int
    #: how far into the next length (wall-clock ms after the wall touch) the stop begins.
    offsetAfterWallMs: int
    durationMs: int


@dataclass(frozen=True, slots=True)
class UnreliableWindow:
    """A span (anchored after a wall) with degraded position/time confidence."""

    afterLengthIndex: int
    offsetAfterWallMs: int
    durationMs: int
    positionNoiseM: float = 2.5


@dataclass(frozen=True, slots=True)
class VirtualSwimResult:
    """Full deterministic output of one tick-simulated swim."""

    observations: tuple[SwimmerObservation, ...]
    wallTouches: tuple[WallTouch, ...]
    #: wall-clock (startMs, endMs) of the realized stop window, if any.
    stopRealized: tuple[int, int] | None = field(default=None)
    #: wall-clock (startMs, endMs) of the realized planned-rest window, if any.
    restRealized: tuple[int, int] | None = field(default=None)


def simulate_swim(
    *,
    config: VirtualSwimmerConfig,
    pool_length_m: int,
    total_distance_m: float,
    target_distance_at_active_ms: Callable[[int], float],
    target_speed_at_distance: Callable[[float], float],
    phase_type_at_distance: Callable[[float], str],
    stop: StopWindow | None = None,
    rest: RestWindow | None = None,
    unreliable: UnreliableWindow | None = None,
    max_ticks: int = 200_000,
) -> VirtualSwimResult:
    """Run the deterministic tick simulation of one swim.

    ``target_distance_at_active_ms`` and ``target_speed_at_distance`` are REAL swimcore
    timeline queries provided by the harness (the swimmer never re-implements the plan).
    The sim clock advances manually tick by tick; wall crossings are interpolated inside
    the crossing tick. No wall-clock time, no sleeping, no global randomness.
    """
    rng = _SplitMix64(config.seed)
    tick = config.tickMs
    observations: list[SwimmerObservation] = []
    touches: list[WallTouch] = []

    now_ms = 0
    active_ms = 0  # swimmer's own swimming-time axis (excludes planned rest)
    true_d = 0.0
    dwell_until_ms = 0  # turn delay / planned rest dwell
    rest_window: tuple[int, int] | None = None
    stop_window: tuple[int, int] | None = None
    unreliable_window: tuple[int, int] | None = None
    walls_total = int(round(total_distance_m / pool_length_m))

    def in_window(w: tuple[int, int] | None) -> bool:
        return w is not None and w[0] <= now_ms < w[1]

    while len(touches) < walls_total and len(observations) < max_ticks:
        planned_rest = in_window(rest_window)
        stopped = in_window(stop_window)
        unreliable_now = in_window(unreliable_window)
        dwelling = now_ms < dwell_until_ms

        # ghost target axis: the ghost does not run during schedule-level planned rest,
        # but it DOES keep running through an unplanned stop (normal domain behaviour).
        rest_elapsed = 0
        if rest_window is not None:
            rest_elapsed = max(0, min(now_ms, rest_window[1]) - rest_window[0])
        ghost_active_ms = max(0, now_ms - rest_elapsed)
        target_d = min(target_distance_at_active_ms(ghost_active_ms), total_distance_m)
        target_v = target_speed_at_distance(min(true_d, total_distance_m))

        if planned_rest or stopped or dwelling:
            v = 0.0
        else:
            fatigue = max(1.0 - config.fatigueSlopePer100M * (true_d / 100.0), 0.05)
            v = target_v * config.baseResponseRatio * fatigue
            v += rng.gauss(0.0, config.noiseStdMps)
            v = min(max(v, config.minimumActualSpeedMps), config.maximumActualSpeedMps)

        # estimated (visual-only) position: never the official distance
        est_d = true_d
        quality = "HIGH"
        if unreliable_now:
            quality = "LOW"
            est_d = max(
                0.0, true_d + rng.gauss(0.0, unreliable.positionNoiseM if unreliable else 0.0)
            )

        observations.append(
            SwimmerObservation(
                wallTimeMs=now_ms,
                activeTimeMs=active_ms,
                actualDistanceM=round(est_d, 6),
                actualSpeedMps=round(v, 6),
                targetDistanceM=round(target_d, 6),
                targetSpeedMps=round(target_v, 6),
                gapM=round(target_d - true_d, 6),
                phaseType=phase_type_at_distance(min(true_d, total_distance_m)),
                positionQuality=quality,
                plannedRest=planned_rest,
            )
        )

        # advance one tick, interpolating any official wall crossing inside it
        d_next = true_d + v * (tick / 1000.0)
        next_wall_index = len(touches)  # 0-based lengthIndex of the next wall to cross
        next_wall_d = float((next_wall_index + 1) * pool_length_m)
        if v > 0.0 and d_next >= next_wall_d - 1e-9:
            frac = (next_wall_d - true_d) / (d_next - true_d)
            cross_ms = now_ms + int(round(frac * tick))
            cross_ms = max(cross_ms, now_ms + 1)
            touches.append(
                WallTouch(
                    lengthIndex=next_wall_index,
                    distanceM=min(next_wall_d, total_distance_m),
                    wallTimestampMs=cross_ms,
                )
            )
            true_d = next_wall_d
            # anchored windows triggered by this wall
            if rest is not None and rest.afterLengthIndex == next_wall_index:
                rest_window = (cross_ms, cross_ms + rest.durationMs)
            if stop is not None and stop.afterLengthIndex == next_wall_index:
                start = cross_ms + stop.offsetAfterWallMs
                stop_window = (start, start + stop.durationMs)
            if unreliable is not None and unreliable.afterLengthIndex == next_wall_index:
                start = cross_ms + unreliable.offsetAfterWallMs
                unreliable_window = (start, start + unreliable.durationMs)
            if config.turnDelayMs > 0 and len(touches) < walls_total:
                dwell_until_ms = cross_ms + config.turnDelayMs
        else:
            true_d = d_next

        now_ms += tick
        if not planned_rest:
            active_ms += tick

    if len(touches) < walls_total:
        raise RuntimeError(
            f"virtual swimmer did not finish: {len(touches)}/{walls_total} walls in "
            f"{len(observations)} ticks"
        )
    return VirtualSwimResult(
        observations=tuple(observations),
        wallTouches=tuple(touches),
        stopRealized=stop_window,
        restRealized=rest_window,
    )
