"""Provenance and run manifests for simulator-produced journals (Commit 8, corrected).

Every simulation run is stamped with a :class:`SimulationRunManifest` (§2.9):
``synthetic = True`` always — synthetic data is NEVER production performance evidence and
never external-dataset training evidence — and a fully deterministic ``runId`` derived
from the scenario identity/version/digest, seed, workout digest, every selected or replacement profile digest, and analytics-policy digest (no timestamps, no UUIDs). The legacy
:class:`SimulationProvenance` lineage block is retained for external-data publication
planning (ADR-032).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.enums import ExternalDataDomain, PaceCurveRepresentation
from contracts.pace_profiles import ApprovedPaceProfile
from swimcore.pacing.continuous_profile_compiler import CONTINUOUS_COMPILER_VERSION

#: Transformation version stamped on simulator provenance (bump on generation changes).
SIMULATION_TRANSFORMATION_VERSION = "sim-transform-1.1.0"

#: Simulator model version (virtual swimmer + scenario semantics).
SIMULATOR_VERSION = "simulator-2.0.0"


def deterministic_run_id(
    *,
    scenario_id: str,
    scenario_version: str,
    scenario_digest: str,
    seed: int,
    workout_ref: str,
    workout_digest: str,
    profile_digests: dict[str, str],
    selected_profile_id: str,
    selected_profile_version: str,
    replacement_profile_id: str | None,
    replacement_profile_version: str | None,
    analytics_policy_digest: str,
    harness_version: str,
) -> str:
    """Hash every deterministic simulator input that can change emitted artifacts."""
    payload = {
        "analyticsPolicyDigest": analytics_policy_digest,
        "harnessVersion": harness_version,
        "profileDigests": dict(sorted(profile_digests.items())),
        "replacementProfileId": replacement_profile_id,
        "replacementProfileVersion": replacement_profile_version,
        "scenarioDigest": scenario_digest,
        "scenarioId": scenario_id,
        "scenarioVersion": scenario_version,
        "seed": seed,
        "selectedProfileId": selected_profile_id,
        "selectedProfileVersion": selected_profile_version,
        "simulatorVersion": SIMULATOR_VERSION,
        "workoutDigest": workout_digest,
        "workoutRef": workout_ref,
    }
    material = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class SimulationRunManifest:
    """Deterministic identity of one simulation run (§2.9)."""

    synthetic: bool
    scenarioId: str
    scenarioVersion: str
    seed: int
    simulatorVersion: str
    harnessVersion: str
    workoutRef: str
    workoutDigest: str
    scenarioDigest: str
    analyticsPolicyDigest: str
    profileDigests: dict[str, str]
    profileId: str
    profileVersion: str
    replacementProfileId: str | None
    replacementProfileVersion: str | None
    curveRepresentation: str | None
    compilerVersion: str
    runId: str

    def as_dict(self) -> dict[str, object]:
        return {
            "synthetic": self.synthetic,
            "scenarioId": self.scenarioId,
            "scenarioVersion": self.scenarioVersion,
            "seed": self.seed,
            "simulatorVersion": self.simulatorVersion,
            "harnessVersion": self.harnessVersion,
            "workoutRef": self.workoutRef,
            "workoutDigest": self.workoutDigest,
            "scenarioDigest": self.scenarioDigest,
            "analyticsPolicyDigest": self.analyticsPolicyDigest,
            "profileDigests": dict(sorted(self.profileDigests.items())),
            "profileId": self.profileId,
            "profileVersion": self.profileVersion,
            "replacementProfileId": self.replacementProfileId,
            "replacementProfileVersion": self.replacementProfileVersion,
            "curveRepresentation": self.curveRepresentation,
            "compilerVersion": self.compilerVersion,
            "runId": self.runId,
        }


@dataclass(frozen=True, slots=True)
class SimulationProvenance:
    """Deterministic lineage for one simulated journal (external-data planning, ADR-032)."""

    scenarioName: str
    seed: int
    sessionId: str
    harnessVersion: str
    compilerVersion: str
    transformationVersion: str
    domain: ExternalDataDomain
    profileId: str
    profileVersion: str
    profileSchemaVersion: str
    curveRepresentation: str | None
    replacementProfileId: str | None
    replacementProfileVersion: str | None
    eventCount: int
    usedRealHumanData: bool
    licenseVerified: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "scenarioName": self.scenarioName,
            "seed": self.seed,
            "sessionId": self.sessionId,
            "harnessVersion": self.harnessVersion,
            "compilerVersion": self.compilerVersion,
            "transformationVersion": self.transformationVersion,
            "domain": self.domain.value,
            "profileId": self.profileId,
            "profileVersion": self.profileVersion,
            "profileSchemaVersion": self.profileSchemaVersion,
            "curveRepresentation": self.curveRepresentation,
            "replacementProfileId": self.replacementProfileId,
            "replacementProfileVersion": self.replacementProfileVersion,
            "eventCount": self.eventCount,
            "usedRealHumanData": self.usedRealHumanData,
            "licenseVerified": self.licenseVerified,
        }


def _representation_of(
    profile: ApprovedPaceProfile | ApprovedContinuousPaceProfile,
) -> tuple[str, str | None]:
    if isinstance(profile, ApprovedContinuousPaceProfile):
        rep: PaceCurveRepresentation = profile.curve.representation
        return "1.1", rep.value
    return "1.0", None


def build_run_manifest(
    *,
    scenario_id: str,
    scenario_version: str,
    scenario_digest: str,
    seed: int,
    harness_version: str,
    workout_ref: str,
    profile: ApprovedPaceProfile | ApprovedContinuousPaceProfile,
    replacement_profile: ApprovedContinuousPaceProfile | None,
    workout_digest: str,
    profile_digests: dict[str, str],
    analytics_policy_digest: str,
) -> SimulationRunManifest:
    """Build the deterministic run manifest. ``synthetic`` is always True."""
    _schema, representation = _representation_of(profile)
    replacement_id = replacement_profile.profileId if replacement_profile is not None else None
    replacement_version = (
        replacement_profile.profileVersion if replacement_profile is not None else None
    )
    return SimulationRunManifest(
        synthetic=True,
        scenarioId=scenario_id,
        scenarioVersion=scenario_version,
        seed=seed,
        simulatorVersion=SIMULATOR_VERSION,
        harnessVersion=harness_version,
        workoutRef=workout_ref,
        workoutDigest=workout_digest,
        scenarioDigest=scenario_digest,
        analyticsPolicyDigest=analytics_policy_digest,
        profileDigests=dict(sorted(profile_digests.items())),
        profileId=profile.profileId,
        profileVersion=profile.profileVersion,
        replacementProfileId=replacement_id,
        replacementProfileVersion=replacement_version,
        curveRepresentation=representation,
        compilerVersion=CONTINUOUS_COMPILER_VERSION,
        runId=deterministic_run_id(
            scenario_id=scenario_id,
            scenario_version=scenario_version,
            scenario_digest=scenario_digest,
            seed=seed,
            workout_ref=workout_ref,
            workout_digest=workout_digest,
            profile_digests=profile_digests,
            selected_profile_id=profile.profileId,
            selected_profile_version=profile.profileVersion,
            replacement_profile_id=replacement_id,
            replacement_profile_version=replacement_version,
            analytics_policy_digest=analytics_policy_digest,
            harness_version=harness_version,
        ),
    )


def build_provenance(
    *,
    scenario_name: str,
    seed: int,
    session_id: str,
    harness_version: str,
    profile: ApprovedPaceProfile | ApprovedContinuousPaceProfile,
    replacement_profile: ApprovedContinuousPaceProfile | None,
    event_count: int,
) -> SimulationProvenance:
    """Build the provenance block for one deterministic simulation run."""
    schema_version, representation = _representation_of(profile)
    return SimulationProvenance(
        scenarioName=scenario_name,
        seed=seed,
        sessionId=session_id,
        harnessVersion=harness_version,
        compilerVersion=CONTINUOUS_COMPILER_VERSION,
        transformationVersion=SIMULATION_TRANSFORMATION_VERSION,
        # Synthetic until a real user consents to publish their own session.
        domain=ExternalDataDomain.SYNTHETIC_SIMULATION,
        profileId=profile.profileId,
        profileVersion=profile.profileVersion,
        profileSchemaVersion=schema_version,
        curveRepresentation=representation,
        replacementProfileId=(
            replacement_profile.profileId if replacement_profile is not None else None
        ),
        replacementProfileVersion=(
            replacement_profile.profileVersion if replacement_profile is not None else None
        ),
        eventCount=event_count,
        # The simulator never ingests real human data; a real publication step must set
        # licenseVerified explicitly after verification (never assumed here).
        usedRealHumanData=False,
        licenseVerified=False,
    )
