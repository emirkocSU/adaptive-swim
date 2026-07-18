"""Deterministic SafetyController (Commit 6): the mandatory gate for pace changes."""

from swimcore.control.errors import InvalidSafetyContextError, SafetyControlError
from swimcore.control.safety import SafetyController
from swimcore.control.types import (
    ControlDecision,
    PaceChangeRequest,
    SafetyContext,
    SafetyDecision,
    SafetyReasonCode,
)

__all__ = [
    "ControlDecision",
    "InvalidSafetyContextError",
    "PaceChangeRequest",
    "SafetyContext",
    "SafetyControlError",
    "SafetyController",
    "SafetyDecision",
    "SafetyReasonCode",
]
