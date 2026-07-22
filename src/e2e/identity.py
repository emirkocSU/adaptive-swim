"""Deterministic identities for the Phase 1 release closure.

The run identity covers every declared deterministic input that can change runtime or
analytics output. It intentionally contains no path, wall-clock time, UUID or random value.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def deterministic_run_id(
    *,
    case_id: str,
    case_version: str,
    seed: int,
    workout_digest: str,
    source_workout_digest: str | None,
    profile_digests: Mapping[str, str],
    selected_profile_id: str,
    selected_profile_version: str,
    replacement_profile_id: str | None,
    replacement_profile_version: str | None,
    scenario_version: str,
    scenario_digest: str,
    analytics_policy_digest: str,
    runner_version: str,
) -> str:
    """Return the content-addressed identity of one deterministic e2e run."""
    payload = {
        "analyticsPolicyDigest": analytics_policy_digest,
        "caseId": case_id,
        "caseVersion": case_version,
        "profileDigests": dict(sorted(profile_digests.items())),
        "replacementProfileId": replacement_profile_id,
        "replacementProfileVersion": replacement_profile_version,
        "runnerVersion": runner_version,
        "scenarioDigest": scenario_digest,
        "scenarioVersion": scenario_version,
        "seed": seed,
        "selectedProfileId": selected_profile_id,
        "selectedProfileVersion": selected_profile_version,
        "sourceWorkoutDigest": source_workout_digest,
        "workoutDigest": workout_digest,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["deterministic_run_id"]
