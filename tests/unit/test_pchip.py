"""PCHIP interpolation tests (Commit 8 §36)."""

from __future__ import annotations

import pytest

from swimcore.pacing.pchip import PchipError, build_pchip


def test_exact_knot_interpolation() -> None:
    xs = (0.0, 25.0, 50.0, 75.0, 100.0)
    ys = (1.2, 1.3, 1.25, 1.35, 1.4)
    p = build_pchip(xs, ys)
    for x, y in zip(xs, ys, strict=True):
        assert abs(p.evaluate(x) - y) < 1e-12


def test_deterministic_coefficients() -> None:
    xs = (0.0, 30.0, 60.0, 100.0)
    ys = (1.1, 1.4, 1.2, 1.5)
    a = build_pchip(xs, ys)
    b = build_pchip(xs, ys)
    assert a.derivatives == b.derivatives
    assert a.ys == b.ys


def test_no_adjacent_value_overshoot() -> None:
    xs = (0.0, 25.0, 50.0, 75.0, 100.0)
    ys = (1.2, 1.3, 1.25, 1.35, 1.4)
    p = build_pchip(xs, ys)
    # sample each segment densely; value must stay within the segment's knot value range
    for i in range(len(xs) - 1):
        lo = min(ys[i], ys[i + 1])
        hi = max(ys[i], ys[i + 1])
        for k in range(101):
            x = xs[i] + (xs[i + 1] - xs[i]) * k / 100.0
            v = p.evaluate(x)
            assert lo - 1e-9 <= v <= hi + 1e-9


def test_positive_input_positive_output() -> None:
    p = build_pchip((0.0, 50.0, 100.0), (1.2, 1.3, 1.1))
    for k in range(101):
        assert p.evaluate(k) > 0.0


def test_two_knots_linear() -> None:
    p = build_pchip((0.0, 100.0), (1.0, 2.0))
    assert abs(p.evaluate(50.0) - 1.5) < 1e-12


def test_needs_two_knots() -> None:
    with pytest.raises(PchipError):
        build_pchip((0.0,), (1.0,))


def test_strictly_increasing_required() -> None:
    with pytest.raises(PchipError):
        build_pchip((0.0, 50.0, 50.0), (1.0, 1.1, 1.2))


def test_rejects_non_finite() -> None:
    with pytest.raises(PchipError):
        build_pchip((0.0, float("inf")), (1.0, 1.2))
    with pytest.raises(PchipError):
        build_pchip((0.0, 50.0), (1.0, float("nan")))


def test_derivative_is_finite() -> None:
    p = build_pchip((0.0, 25.0, 50.0, 100.0), (1.2, 1.35, 1.25, 1.4))
    for k in range(101):
        d = p.derivative(float(k))
        assert d == d  # not NaN


def test_evaluate_out_of_domain_rejected() -> None:
    p = build_pchip((0.0, 100.0), (1.2, 1.3))
    with pytest.raises(PchipError):
        p.evaluate(-5.0)
    with pytest.raises(PchipError):
        p.evaluate(200.0)
