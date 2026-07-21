"""Deterministic selection of the live pace profile (ADR-034 authority order).

Priority (highest first):
    COACH_AUTHORED > COACH_APPROVED_MODEL > DEFAULT_MODEL_GENERATED
DEFAULT_MODEL_GENERATED is eligible only with an explicit opt-in policy. TEMPLATE and
LEGACY_SEGMENTS are positioned below the model tiers. Only approval-eligible candidates are
considered; a coach-locked winner blocks any automatic ML/rule override downstream.

Pure and deterministic: no I/O, no randomness, no ambiguity — an unresolved tie raises
rather than silently picking one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from contracts.enums import PaceProfileSource


class _SelectableProfile(Protocol):
    """Minimal surface the selector needs (satisfied by both 1.0 and 1.1 profiles)."""

    source: PaceProfileSource

    @property
    def is_live_eligible(self) -> bool: ...


class PaceProfileSelectionError(Exception):
    """Base class for profile-selection errors."""


class NoLiveEligiblePaceProfileError(PaceProfileSelectionError):
    pass


class AmbiguousPaceProfileSelectionError(PaceProfileSelectionError):
    pass


class CoachLockedProfileOverrideError(PaceProfileSelectionError):
    pass


@dataclass(frozen=True, slots=True)
class ProfileSelectionPolicy:
    """Selection policy. Default-model profiles require an explicit opt-in."""

    allowDefaultModelGenerated: bool = False


#: Lower number = higher authority.
_PRIORITY: dict[PaceProfileSource, int] = {
    PaceProfileSource.COACH_AUTHORED: 0,
    PaceProfileSource.COACH_APPROVED_MODEL: 1,
    PaceProfileSource.DEFAULT_MODEL_GENERATED: 2,
    PaceProfileSource.TEMPLATE: 3,
    PaceProfileSource.LEGACY_SEGMENTS: 4,
}


def select_live_pace_profile[T: _SelectableProfile](
    candidates: list[T],
    policy: ProfileSelectionPolicy | None = None,
) -> T:
    """Return the single authoritative live profile, or raise on emptiness/ambiguity.

    Accepts either legacy ``ApprovedPaceProfile`` (1.0) or ``ApprovedContinuousPaceProfile``
    (1.1) candidates — both expose ``source`` and ``is_live_eligible``; the ADR-034 authority
    order and default-model opt-in are unchanged.
    """
    pol = policy if policy is not None else ProfileSelectionPolicy()

    eligible = [c for c in candidates if c.is_live_eligible]
    # default-model profiles require explicit opt-in
    eligible = [
        c
        for c in eligible
        if c.source is not PaceProfileSource.DEFAULT_MODEL_GENERATED
        or pol.allowDefaultModelGenerated
    ]
    if not eligible:
        raise NoLiveEligiblePaceProfileError(
            "no live-eligible pace profile among candidates "
            "(check approval status and default-model opt-in)"
        )

    best_rank = min(_PRIORITY[c.source] for c in eligible)
    winners = [c for c in eligible if _PRIORITY[c.source] == best_rank]
    if len(winners) > 1:
        raise AmbiguousPaceProfileSelectionError(
            f"{len(winners)} candidates share the highest authority "
            f"({winners[0].source}); selection is ambiguous"
        )
    return winners[0]
