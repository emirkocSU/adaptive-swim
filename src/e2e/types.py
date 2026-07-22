"""Immutable inputs and outputs of one Phase 1 vertical-slice run (ADR-041).

These types are orchestration data only. Every domain decision still belongs to
``contracts``, ``swimcore``, ``persistence``, ``simulator`` and ``analytics``; the e2e layer
merely names the case, runs the real components in order and records what happened.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from analytics.types import ApprovedPaceProfileVersion
from contracts.enums import StartMode, WorkoutGoal
from contracts.session_report import SessionReportV1_1
from contracts.workout import WorkoutTemplateV1_0, WorkoutTemplateV1_1
from e2e.errors import E2ECaseError
from e2e.manifest import Phase1VerificationManifest
from simulator.harness import CommandOutcome, LiveFinalState, SimulationScenario
from swimcore.replay.state import HistoricalSessionState

#: Version of the e2e runner semantics; part of the deterministic run identity.
E2E_RUNNER_VERSION = "e2e-runner-1.1.0"

#: Canonical bundle member names written for every case.
BUNDLE_MANIFEST_FILE = "manifest.json"
BUNDLE_JOURNAL_FILE = "journal.jsonl"
BUNDLE_REPORT_FILE = "session-report.json"
BUNDLE_COMMAND_OUTCOMES_FILE = "command-outcomes.json"
BUNDLE_OBSERVATIONS_FILE = "observations.jsonl"
BUNDLE_SHA256_FILE = "artifact-sha256.txt"

REQUIRED_BUNDLE_FILES = (
    BUNDLE_MANIFEST_FILE,
    BUNDLE_JOURNAL_FILE,
    BUNDLE_REPORT_FILE,
    BUNDLE_COMMAND_OUTCOMES_FILE,
    BUNDLE_SHA256_FILE,
)


@dataclass(frozen=True, slots=True)
class E2EAnalyticsPolicy:
    """The analytics knobs a case pins. Mirrors ``ReportBuildContext`` tunables.

    Kept as a separate immutable record so the case (and therefore the deterministic run
    identity and the manifest) does not depend on a mutable profile registry.
    """

    analyticsVersion: str = "analytics-1.0.0"
    reportBuilderVersion: str = "report-builder-1.0.0"
    reportVersion: str = "commit-9"
    adherenceToleranceSec: float = 0.75
    onTargetTolerancePct: float = 3.0
    curveAdherenceToleranceM: float = 1.0
    minimumTrustedCurveObservations: int = 3
    minimumCurveCoverageRatio: float = 0.25
    maximumLowQualityObservationRatio: float = 0.05
    minimumConsecutiveDecliningSplits: int = 2
    minimumDeclinePct: float = 2.0
    unexpectedCollapseMarginPct: float = 3.0
    minimumPacingShapeSplits: int = 3
    minimumSensorSamplesForTrend: int = 3


@dataclass(frozen=True, slots=True)
class Phase1ExpectedOutcome:
    """Case-specific expectations checked in addition to the global invariant matrix."""

    lifecycleState: str = "COMPLETED"
    officialDistanceM: float | None = None
    poolLengthM: int | None = None
    officialLengthCount: int | None = None
    stopPauseCount: int = 0
    stoppedDurationMs: int | None = None
    coachResetAppliedCount: int = 0
    rejectedCommandCount: int = 0
    idempotentReplayCount: int = 0
    finalProfileId: str | None = None
    finalProfileSource: str | None = None
    finalProfileCoachLocked: bool | None = None
    #: When set, the continuous-curve analysis must (not) be available.
    continuousCurveAvailable: bool | None = None
    #: When set, the report must carry exactly these dataset evidence asset ids.
    datasetEvidenceAssetIds: tuple[str, ...] | None = None
    #: When set, the profile provenance must declare this curve evidence level.
    curveEvidenceLevel: str | None = None
    #: When True, the profile must NOT claim measured continuous-velocity ground truth.
    requireNotGroundTruth: bool = False


@dataclass(frozen=True, slots=True)
class Phase1E2ECase:
    """One full Phase 1 vertical-slice case definition."""

    caseId: str
    caseVersion: str
    seed: int
    workout: WorkoutTemplateV1_1
    paceProfiles: tuple[ApprovedPaceProfileVersion, ...]
    selectedProfileId: str
    scenario: SimulationScenario
    sourceWorkoutV1_0: WorkoutTemplateV1_0 | None = None
    sourceWorkoutDefaultStartMode: StartMode | None = None
    sourceWorkoutGoal: WorkoutGoal | None = None
    analyticsPolicy: E2EAnalyticsPolicy = field(default_factory=E2EAnalyticsPolicy)
    expectedOutcome: Phase1ExpectedOutcome = field(default_factory=Phase1ExpectedOutcome)
    description: str = ""
    #: Optional required-failure-scenario slug this case exercises end to end.
    failureScenarioId: str | None = None
    #: Emit the optional ``observations.jsonl`` member for this case.
    emitObservations: bool = False
    #: The same approved plan in its other representation (legacy 1.0 vs migrated 1.1).
    #: Commit 10 runs this partner through a second real aggregate/journal/replay/report
    #: chain; it is not merely compiled for a target-function comparison.
    equivalenceProfile: ApprovedPaceProfileVersion | None = None

    def __post_init__(self) -> None:
        if not self.caseId or not self.caseVersion:
            raise E2ECaseError("caseId and caseVersion are required")
        if not self.paceProfiles:
            raise E2ECaseError(f"{self.caseId}: at least one pace profile is required")
        ids = [profile.profileId for profile in self.paceProfiles]
        if len(set(ids)) != len(ids):
            raise E2ECaseError(f"{self.caseId}: duplicate profile ids in paceProfiles")
        if self.selectedProfileId not in ids:
            raise E2ECaseError(
                f"{self.caseId}: selectedProfileId {self.selectedProfileId!r} is not in "
                f"paceProfiles {ids}"
            )
        if self.scenario.profile.profileId != self.selectedProfileId:
            raise E2ECaseError(
                f"{self.caseId}: scenario profile {self.scenario.profile.profileId!r} != "
                f"selectedProfileId {self.selectedProfileId!r}"
            )
        if self.scenario.workout is not self.workout:
            raise E2ECaseError(f"{self.caseId}: scenario workout must be the case workout")
        legacy_fields = (
            self.sourceWorkoutV1_0,
            self.sourceWorkoutDefaultStartMode,
            self.sourceWorkoutGoal,
        )
        if any(item is not None for item in legacy_fields) and any(
            item is None for item in legacy_fields
        ):
            raise E2ECaseError(
                f"{self.caseId}: legacy workout source, start mode and goal are all required"
            )
        replacement = self.scenario.replacementProfile
        if replacement is not None and replacement.profileId not in ids:
            raise E2ECaseError(
                f"{self.caseId}: replacement profile {replacement.profileId!r} must be "
                "declared in paceProfiles"
            )
        partner = self.equivalenceProfile
        if partner is not None and partner.profileId != self.selectedProfileId:
            raise E2ECaseError(
                f"{self.caseId}: equivalenceProfile {partner.profileId!r} must describe the "
                f"selected profile {self.selectedProfileId!r}"
            )

    def profile_by_id(self, profile_id: str) -> ApprovedPaceProfileVersion:
        for profile in self.paceProfiles:
            if profile.profileId == profile_id:
                return profile
        raise E2ECaseError(f"{self.caseId}: unknown profile id {profile_id!r}")


@dataclass(frozen=True, slots=True)
class Phase1E2EResult:
    """Everything one vertical-slice run produced and proved."""

    caseId: str
    caseVersion: str
    seed: int
    runId: str
    workoutDigest: str
    sourceWorkoutDigest: str | None
    profileDigest: str
    profileDigests: Mapping[str, str]
    scenarioDigest: str
    analyticsPolicyDigest: str
    compiledTimelineDigest: str
    commands: tuple[str, ...]
    commandOutcomes: tuple[CommandOutcome, ...]
    eventBatches: tuple[tuple[int, ...], ...]
    eventCount: int
    journalPath: Path
    journalSha256: str
    liveFinalState: LiveFinalState
    replayFinalState: HistoricalSessionState
    liveReplayMatch: bool
    sessionReport: SessionReportV1_1
    sessionReportPath: Path
    sessionReportSha256: str
    verificationManifest: Phase1VerificationManifest
    verificationManifestPath: Path
    verificationManifestSha256: str
    allChecksPassed: bool
    warnings: tuple[str, ...]
    bundleDirectory: Path
    commandOutcomesPath: Path
    artifactDigestPath: Path
    observationsPath: Path | None = None


__all__ = [
    "BUNDLE_COMMAND_OUTCOMES_FILE",
    "BUNDLE_JOURNAL_FILE",
    "BUNDLE_MANIFEST_FILE",
    "BUNDLE_OBSERVATIONS_FILE",
    "BUNDLE_REPORT_FILE",
    "BUNDLE_SHA256_FILE",
    "E2E_RUNNER_VERSION",
    "REQUIRED_BUNDLE_FILES",
    "E2EAnalyticsPolicy",
    "Phase1E2ECase",
    "Phase1E2EResult",
    "Phase1ExpectedOutcome",
]
