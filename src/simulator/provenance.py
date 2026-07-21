"""Provenance for simulator-produced journals (Commit 8, ADR-032/ADR-038).

A simulated session journal may later be published as a ``SYNTHETIC_SIMULATION`` (or, once
consented, ``ADAPTIVE_SWIM_SESSION``) external-data record. This module records the lineage
needed for that: the deterministic seed, harness + compiler versions, the source profile
identity/representation, and a flag that the run used no real human data. It is pure and
carries no license claim (a real publication step performs explicit license verification).
"""

from __future__ import annotations

from dataclasses import dataclass

from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.enums import ExternalDataDomain, PaceCurveRepresentation
from contracts.pace_profiles import ApprovedPaceProfile
from swimcore.pacing.continuous_profile_compiler import CONTINUOUS_COMPILER_VERSION

#: Transformation version stamped on simulator provenance (bump on generation changes).
SIMULATION_TRANSFORMATION_VERSION = "sim-transform-1.0.0"


@dataclass(frozen=True, slots=True)
class SimulationProvenance:
    """Deterministic lineage for one simulated journal."""

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
