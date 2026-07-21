"""Deterministic evaluation of an approved continuous pace curve (ADR-038).

Wraps the authoritative :mod:`swimcore.pacing.pchip` evaluator (or a constant-speed lookup)
behind one interface returning target *speed* (m/s) at a distance. The physical-bounds
policy is a typed, optional validation context — this product decision deliberately fixes no
concrete human-performance speed/acceleration numbers, so none are invented here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from contracts.continuous_pace import ContinuousPaceCurve
from contracts.enums import PaceCurveRepresentation
from swimcore.pacing.errors import InvalidPaceCurveError
from swimcore.pacing.pchip import PchipError, PchipInterpolator, build_pchip


@dataclass(frozen=True, slots=True)
class ContinuousCurveValidationContext:
    """Optional physical bounds. Positivity/finiteness are enforced with or without this.

    When provided, all supplied bounds are checked; when absent the compiler still performs
    mathematical validation but records ``physicalBoundsChecked = false``.
    """

    minimumSpeedMps: float | None = None
    maximumSpeedMps: float | None = None
    maximumAccelerationMps2: float | None = None
    maximumDecelerationMps2: float | None = None
    maximumSpeedGradientPerM: float | None = None

    @property
    def has_any_bound(self) -> bool:
        return any(
            v is not None
            for v in (
                self.minimumSpeedMps,
                self.maximumSpeedMps,
                self.maximumAccelerationMps2,
                self.maximumDecelerationMps2,
                self.maximumSpeedGradientPerM,
            )
        )


@dataclass(frozen=True, slots=True)
class EvaluableCurve:
    """A representation-agnostic speed(distance) evaluator built from an approved curve."""

    representation: PaceCurveRepresentation
    total_distance_m: float
    _pchip: PchipInterpolator | None
    _segments: tuple[tuple[float, float, float], ...]  # (fromM, toM, speed)
    knot_distances: tuple[float, ...]

    def speed_at(self, distance_m: float) -> float:
        if not math.isfinite(distance_m):
            raise InvalidPaceCurveError(f"distance must be finite, got {distance_m}")
        d = min(max(distance_m, 0.0), self.total_distance_m)
        if self._pchip is not None:
            try:
                speed = self._pchip.evaluate(d)
            except PchipError as exc:
                raise InvalidPaceCurveError(str(exc)) from exc
        else:
            speed = self._constant_speed_at(d)
        if not math.isfinite(speed):
            raise InvalidPaceCurveError(f"curve produced non-finite speed at {distance_m}")
        if speed <= 0.0:
            raise InvalidPaceCurveError(
                f"curve produced non-positive speed {speed} at {distance_m}"
            )
        return speed

    def gradient_at(self, distance_m: float) -> float:
        """d(speed)/d(distance) — 0 for constant-speed segments, PCHIP derivative otherwise."""
        if self._pchip is not None:
            try:
                return self._pchip.derivative(min(max(distance_m, 0.0), self.total_distance_m))
            except PchipError as exc:
                raise InvalidPaceCurveError(str(exc)) from exc
        return 0.0

    def _constant_speed_at(self, d: float) -> float:
        for _from_m, to_m, speed in self._segments:
            if d <= to_m + 1e-9:
                return speed
        return self._segments[-1][2]


def build_evaluable_curve(curve: ContinuousPaceCurve) -> EvaluableCurve:
    """Build the deterministic speed evaluator for an approved curve."""
    if curve.representation is PaceCurveRepresentation.PCHIP:
        distances = tuple(k.distanceM for k in curve.knots)
        speeds = tuple(k.targetSpeedMps for k in curve.knots)
        try:
            interp = build_pchip(distances, speeds)
        except PchipError as exc:
            raise InvalidPaceCurveError(str(exc)) from exc
        return EvaluableCurve(
            representation=curve.representation,
            total_distance_m=distances[-1],
            _pchip=interp,
            _segments=(),
            knot_distances=distances,
        )
    segments = tuple((s.fromM, s.toM, s.targetSpeedMps) for s in curve.segments)
    return EvaluableCurve(
        representation=curve.representation,
        total_distance_m=segments[-1][1],
        _pchip=None,
        _segments=segments,
        knot_distances=tuple(s.fromM for s in curve.segments) + (segments[-1][1],),
    )
