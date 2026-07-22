"""Analytic physical-bound verification for continuous pace curves (§2.7, ADR-038/039).

Sampling on a 0.10 m grid is NOT authoritative proof that a curve respects its physical
bounds: a violation can sit between two grid points. This module verifies speed, speed
gradient and acceleration/deceleration bounds *analytically* per PCHIP interval:

- **Speed extrema**: each PCHIP interval is a cubic ``v(t)``; interior extrema are the real
  roots of the quadratic ``v'(t) = 0`` (closed form).
- **Gradient extrema**: ``dv/dd`` extrema come from the root of the linear ``v''(t) = 0``
  (closed form) plus interval endpoints.
- **Acceleration** ``a(d) = v · dv/dd``: verified with branch-and-bound whose
  per-subinterval upper bound ``|a| ≤ max|v| · max|dv/dd|`` is computed from the
  closed-form extrema above — a true mathematical bound, never a sample. Subintervals whose
  bound satisfies the limit are certified without pointwise evaluation; only subintervals
  whose bound exceeds the limit are recursively split until the bound certifies them or a
  genuine violation is exhibited. Interior extrema of the differentiable ``a`` occur only
  where ``a' = (v'² + v·v'')/h²`` changes sign, so the recursion cannot skip one.

Reconciliation scales each region's speed uniformly (pace × f → speed / f, gradient / f,
acceleration / f²), so the same analytic verification runs *after* reconciliation with the
region scale applied (§2.6). CONSTANT_SPEED curves have zero gradient/acceleration inside
segments; only their segment speeds are checked.

Pure, deterministic, stdlib-only. Raises :class:`ProfileCompilationError` on violation
(reject, never clamp).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from swimcore.pacing.continuous_curve import ContinuousCurveValidationContext, EvaluableCurve
from swimcore.pacing.pchip import PchipInterpolator
from swimcore.pacing.profile_compiler import ProfileCompilationError

#: Numerical slack for bound comparisons (same order as the compiler's tolerances).
_BOUND_TOL = 1e-9

#: Minimum subinterval width (in t) before branch-and-bound evaluates directly.
_MIN_T_WIDTH = 1e-9

#: Hard recursion depth cap (2^-60 << _MIN_T_WIDTH, never reached in practice).
_MAX_DEPTH = 60


@dataclass(frozen=True, slots=True)
class _Cubic:
    """One PCHIP interval as a cubic in local t ∈ [0, 1]; d = x0 + h·t."""

    x0: float
    h: float
    a3: float
    a2: float
    a1: float
    a0: float

    def v(self, t: float) -> float:
        return ((self.a3 * t + self.a2) * t + self.a1) * t + self.a0

    def dv_dt(self, t: float) -> float:
        return (3.0 * self.a3 * t + 2.0 * self.a2) * t + self.a1

    def gradient(self, t: float) -> float:
        """dv/dd = (dv/dt) / h."""
        return self.dv_dt(t) / self.h

    def acceleration(self, t: float) -> float:
        """a = v · dv/dd (raw, unscaled)."""
        return self.v(t) * self.dv_dt(t) / self.h


def _cubics_of(pchip: PchipInterpolator) -> tuple[_Cubic, ...]:
    out: list[_Cubic] = []
    xs, ys, ms = pchip.xs, pchip.ys, pchip.derivatives
    for i in range(len(xs) - 1):
        h = xs[i + 1] - xs[i]
        y0, y1 = ys[i], ys[i + 1]
        m0, m1 = ms[i], ms[i + 1]
        out.append(
            _Cubic(
                x0=xs[i],
                h=h,
                a3=2.0 * (y0 - y1) + h * (m0 + m1),
                a2=-3.0 * (y0 - y1) - h * (2.0 * m0 + m1),
                a1=h * m0,
                a0=y0,
            )
        )
    return tuple(out)


def _quadratic_roots_in(a: float, b: float, c: float, lo: float, hi: float) -> tuple[float, ...]:
    """Real roots of a·t² + b·t + c = 0 inside [lo, hi] (closed form, deterministic)."""
    roots: list[float] = []
    if abs(a) < 1e-300:
        if abs(b) >= 1e-300:
            roots.append(-c / b)
    else:
        disc = b * b - 4.0 * a * c
        if disc >= 0.0:
            sq = math.sqrt(disc)
            q = -0.5 * (b + math.copysign(sq, b)) if b != 0.0 else 0.5 * sq
            if q != 0.0:
                roots.extend((q / a, c / q))
            else:
                roots.append(0.0)
    return tuple(t for t in roots if math.isfinite(t) and lo - 1e-12 <= t <= hi + 1e-12)


def _speed_candidates(cubic: _Cubic, lo: float, hi: float) -> tuple[float, ...]:
    """t where v may attain an extremum on [lo, hi]: endpoints + v'(t)=0 roots (exact)."""
    interior = _quadratic_roots_in(3.0 * cubic.a3, 2.0 * cubic.a2, cubic.a1, lo, hi)
    return (lo, hi, *interior)


def _gradient_candidates(cubic: _Cubic, lo: float, hi: float) -> tuple[float, ...]:
    """t where dv/dd may attain an extremum on [lo, hi]: endpoints + v''(t)=0 (exact)."""
    cands = [lo, hi]
    if abs(cubic.a3) >= 1e-300:
        t = -cubic.a2 / (3.0 * cubic.a3)
        if lo - 1e-12 <= t <= hi + 1e-12:
            cands.append(t)
    return tuple(cands)


def _scaled_speed_range(cubic: _Cubic, lo: float, hi: float, scale: float) -> tuple[float, float]:
    vals = [cubic.v(t) / scale for t in _speed_candidates(cubic, lo, hi)]
    return min(vals), max(vals)


def _scaled_abs_gradient_max(cubic: _Cubic, lo: float, hi: float, scale: float) -> float:
    return max(abs(cubic.gradient(t)) / scale for t in _gradient_candidates(cubic, lo, hi))


def _fail(message: str) -> None:
    raise ProfileCompilationError(message)


@dataclass(frozen=True, slots=True)
class ScaledRegion:
    """A distance span whose reconciled speed is the raw curve speed / paceScaleFactor.

    ``paceScaleFactor`` is the factor the reconciler multiplied *pace* by.
    """

    fromM: float
    toM: float
    paceScaleFactor: float


def _check_acceleration_over(
    cubic: _Cubic,
    ctx: ContinuousCurveValidationContext,
    scale: float,
    lo: float,
    hi: float,
    label: str,
) -> None:
    max_acc = ctx.maximumAccelerationMps2
    max_dec = ctx.maximumDecelerationMps2
    if max_acc is None and max_dec is None:
        return
    acc_scale = scale * scale  # a scales by 1/f² when speed scales by 1/f

    def scaled_acceleration(t: float) -> float:
        return cubic.acceleration(t) / acc_scale

    def check_value(a: float, where_t: float) -> None:
        d = cubic.x0 + cubic.h * where_t
        if max_acc is not None and a > max_acc + _BOUND_TOL:
            _fail(f"{label}: acceleration {a} at {d} m exceeds bound {max_acc}")
        if max_dec is not None and -a > max_dec + _BOUND_TOL:
            _fail(f"{label}: deceleration {-a} at {d} m exceeds bound {max_dec}")

    # exact candidates: endpoints + speed extrema + gradient extrema
    for t in {*_speed_candidates(cubic, lo, hi), *_gradient_candidates(cubic, lo, hi)}:
        check_value(scaled_acceleration(t), t)

    limit = min(x for x in (max_acc, max_dec) if x is not None)

    def verify(t_lo: float, t_hi: float, depth: int) -> None:
        # mathematical upper bound: |a_s| = |v_s|·|g_s| ≤ max|v_s| · max|g_s| over [t_lo,t_hi]
        v_lo, v_hi = _scaled_speed_range(cubic, t_lo, t_hi, scale)
        v_abs = max(abs(v_lo), abs(v_hi))
        g_abs = _scaled_abs_gradient_max(cubic, t_lo, t_hi, scale)
        bound = v_abs * g_abs
        if bound <= limit + _BOUND_TOL:
            return  # certified analytically — no sampling used as proof
        if t_hi - t_lo <= _MIN_T_WIDTH or depth >= _MAX_DEPTH:
            for t in (t_lo, 0.5 * (t_lo + t_hi), t_hi):
                check_value(scaled_acceleration(t), t)
            return
        mid = 0.5 * (t_lo + t_hi)
        check_value(scaled_acceleration(mid), mid)
        verify(t_lo, mid, depth + 1)
        verify(mid, t_hi, depth + 1)

    verify(lo, hi, 0)


def check_curve_physical_bounds(
    evaluable: EvaluableCurve,
    ctx: ContinuousCurveValidationContext,
    *,
    regions: tuple[ScaledRegion, ...] | None = None,
    stage: str = "pre-reconciliation",
) -> None:
    """Analytically verify ALL supplied physical bounds over the whole curve.

    ``regions`` (post-reconciliation) maps distance spans to their pace scale factors; when
    omitted the raw (unscaled) curve is verified. Raises on the first violation; sampling
    is never the authoritative proof.
    """
    if not ctx.has_any_bound:
        return

    def scale_at(d: float) -> float:
        if not regions:
            return 1.0
        for region in regions:
            if region.fromM - 1e-9 <= d <= region.toM + 1e-9:
                return region.paceScaleFactor
        return regions[-1].paceScaleFactor

    if evaluable._pchip is None:  # noqa: SLF001 - CONSTANT_SPEED: piecewise constant
        for from_m, to_m, speed in evaluable._segments:  # noqa: SLF001
            mid = 0.5 * (from_m + to_m)
            v = speed / scale_at(mid)
            if ctx.minimumSpeedMps is not None and v < ctx.minimumSpeedMps - _BOUND_TOL:
                _fail(f"{stage}: segment speed {v} below bound {ctx.minimumSpeedMps}")
            if ctx.maximumSpeedMps is not None and v > ctx.maximumSpeedMps + _BOUND_TOL:
                _fail(f"{stage}: segment speed {v} above bound {ctx.maximumSpeedMps}")
        return

    for cubic in _cubics_of(evaluable._pchip):  # noqa: SLF001
        # split the PCHIP interval at region boundaries so each piece has one scale factor
        boundaries: list[float] = [cubic.x0, cubic.x0 + cubic.h]
        if regions:
            for region in regions:
                for b in (region.fromM, region.toM):
                    if cubic.x0 + 1e-9 < b < cubic.x0 + cubic.h - 1e-9:
                        boundaries.append(b)
        boundaries = sorted(set(boundaries))
        for j in range(len(boundaries) - 1):
            lo_d, hi_d = boundaries[j], boundaries[j + 1]
            scale = scale_at(0.5 * (lo_d + hi_d))
            lo_t = (lo_d - cubic.x0) / cubic.h
            hi_t = (hi_d - cubic.x0) / cubic.h
            label = f"{stage} [{lo_d:.6g}, {hi_d:.6g}] m"
            v_min, v_max = _scaled_speed_range(cubic, lo_t, hi_t, scale)
            if ctx.minimumSpeedMps is not None and v_min < ctx.minimumSpeedMps - _BOUND_TOL:
                _fail(f"{label}: analytic speed minimum {v_min} below {ctx.minimumSpeedMps}")
            if ctx.maximumSpeedMps is not None and v_max > ctx.maximumSpeedMps + _BOUND_TOL:
                _fail(f"{label}: analytic speed maximum {v_max} above {ctx.maximumSpeedMps}")
            if ctx.maximumSpeedGradientPerM is not None:
                g_max = _scaled_abs_gradient_max(cubic, lo_t, hi_t, scale)
                if g_max > ctx.maximumSpeedGradientPerM + _BOUND_TOL:
                    _fail(
                        f"{label}: analytic |dv/dd| maximum {g_max} exceeds "
                        f"{ctx.maximumSpeedGradientPerM}"
                    )
            _check_acceleration_over(cubic, ctx, scale, lo_t, hi_t, label)


__all__ = ["ScaledRegion", "check_curve_physical_bounds"]
