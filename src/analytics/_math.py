"""Small dependency-free deterministic statistics helpers."""

from __future__ import annotations

import math
from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean requires at least one value")
    return math.fsum(values) / len(values)


def rms(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("rms requires at least one value")
    return math.sqrt(math.fsum(value * value for value in values) / len(values))


def least_squares_slope(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x_bar = mean(xs)
    y_bar = mean(ys)
    denominator = math.fsum((x - x_bar) ** 2 for x in xs)
    if denominator <= 1e-12:
        return None
    numerator = math.fsum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys, strict=True))
    return numerator / denominator


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    x_bar = mean(xs)
    y_bar = mean(ys)
    numerator = math.fsum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys, strict=True))
    x_ss = math.fsum((x - x_bar) ** 2 for x in xs)
    y_ss = math.fsum((y - y_bar) ** 2 for y in ys)
    if x_ss <= 1e-12 or y_ss <= 1e-12:
        return None
    return numerator / math.sqrt(x_ss * y_ss)


def overlap_ms(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))
