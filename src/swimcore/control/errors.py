"""SafetyController domain errors."""

from __future__ import annotations


class SafetyControlError(Exception):
    """Base class for safety-controller errors."""


class InvalidSafetyContextError(SafetyControlError):
    pass
