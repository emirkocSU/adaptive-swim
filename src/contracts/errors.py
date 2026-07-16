"""Validation issue contract (machine-readable output of the semantic validator)."""

from __future__ import annotations

from contracts._base import StrictModel
from contracts.enums import IssueSeverity


class ValidationIssue(StrictModel):
    path: str
    rule: str
    message: str
    severity: IssueSeverity
