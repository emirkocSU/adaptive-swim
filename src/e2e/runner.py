"""Phase 1 full vertical-slice runner (ADR-041).

One call drives the whole authoritative Phase 1 chain with the **real** components:

```
workout + approved profile -> contract validation -> profile selection/authority
  -> deterministic pace compilation -> SessionAggregate -> commands
  -> domain event batches -> append-only JSONL journal -> historical replay
  -> HistoricalSessionState -> deterministic analytics -> canonical SessionReport
  -> verification manifest and hashes
```

There is no second ghost engine, no second replay reducer and no second analytics
implementation: the simulator harness drives the production aggregate and journal, the
report is rebuilt here **from the journal on disk** through the public analytics API, and
the two independently produced reports must be byte-identical.

The runner is deterministic: no wall clock, no randomness of its own, no network. The
output directory never influences artifact bytes.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path

from analytics import (
    ProfileRuntimeContext,
    ReportBuildContext,
    build_session_report,
    encode_session_report,
)
from analytics.identity import canonical_digest_sha256
from contracts.event_log import EventBatchRecord
from contracts.events import EventEnvelope
from contracts.workout import WorkoutTemplateV1_1
from e2e.errors import E2EVerificationError
from e2e.identity import deterministic_run_id
from e2e.manifest import (
    PHASE1_MANIFEST_SCHEMA_VERSION,
    PHASE1_MANIFEST_VERSION,
    CheckStatus,
    Phase1VerificationCheck,
    Phase1VerificationManifest,
    encode_manifest,
    finalize_manifest,
)
from e2e.types import (
    BUNDLE_COMMAND_OUTCOMES_FILE,
    BUNDLE_JOURNAL_FILE,
    BUNDLE_MANIFEST_FILE,
    BUNDLE_OBSERVATIONS_FILE,
    BUNDLE_REPORT_FILE,
    BUNDLE_SHA256_FILE,
    E2E_RUNNER_VERSION,
    Phase1E2ECase,
    Phase1E2EResult,
)
from e2e.verification import (
    check_clock_invariants,
    check_distance_invariants,
    check_event_invariants,
    check_expected_outcome,
    check_migration_equivalence,
    check_profile_invariants,
    check_report_invariants,
    check_state_invariants,
)
from persistence.codec import decode_batch
from persistence.jsonl_event_log import JsonlSessionEventLog
from simulator.harness import SimulationResult, compile_ghost_timeline, run_scenario
from swimcore.pacing.continuous_profile_compiler import CONTINUOUS_COMPILER_VERSION
from swimcore.replay.reducer import replay_session
from swimcore.workout.migrations import migrate_workout_1_0_to_1_1

#: Version of the replay reducer contract this closure was verified against.
REPLAY_VERSION = "replay-1.0.0"

_WORK_DIRECTORY = ".work"


def _resolve_runtime_workout(
    case: Phase1E2ECase,
) -> tuple[WorkoutTemplateV1_1, str | None]:
    """Resolve an optional Workout 1.0 source into the exact runtime Workout 1.1 object."""
    if case.sourceWorkoutV1_0 is None:
        return case.workout, None
    assert case.sourceWorkoutDefaultStartMode is not None
    assert case.sourceWorkoutGoal is not None
    migrated = migrate_workout_1_0_to_1_1(
        case.sourceWorkoutV1_0,
        explicit_default_start_mode=case.sourceWorkoutDefaultStartMode,
        workout_goal=case.sourceWorkoutGoal,
    )
    if canonical_digest_sha256(migrated) != canonical_digest_sha256(case.workout):
        raise E2EVerificationError(
            f"{case.caseId}: Workout 1.0 migration does not equal the declared runtime workout"
        )
    return migrated, canonical_digest_sha256(case.sourceWorkoutV1_0)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _read_batches(journal_path: Path) -> tuple[EventBatchRecord, ...]:
    lines = [line for line in journal_path.read_bytes().split(b"\n") if line.strip()]
    return tuple(decode_batch(line) for line in lines)


def _report_context(
    case: Phase1E2ECase,
    simulation_run_id: str,
    registry: dict[tuple[str, str], ProfileRuntimeContext],
) -> ReportBuildContext:
    policy = case.analyticsPolicy
    return ReportBuildContext(
        analyticsVersion=policy.analyticsVersion,
        reportBuilderVersion=policy.reportBuilderVersion,
        reportVersion=policy.reportVersion,
        adherenceToleranceSec=policy.adherenceToleranceSec,
        onTargetTolerancePct=policy.onTargetTolerancePct,
        curveAdherenceToleranceM=policy.curveAdherenceToleranceM,
        minimumTrustedCurveObservations=policy.minimumTrustedCurveObservations,
        minimumCurveCoverageRatio=policy.minimumCurveCoverageRatio,
        maximumLowQualityObservationRatio=policy.maximumLowQualityObservationRatio,
        minimumConsecutiveDecliningSplits=policy.minimumConsecutiveDecliningSplits,
        minimumDeclinePct=policy.minimumDeclinePct,
        unexpectedCollapseMarginPct=policy.unexpectedCollapseMarginPct,
        minimumPacingShapeSplits=policy.minimumPacingShapeSplits,
        minimumSensorSamplesForTrend=policy.minimumSensorSamplesForTrend,
        simulatorSynthetic=True,
        simulationRunId=simulation_run_id,
        profileRegistry=registry,
    )


def _profile_digests(case: Phase1E2ECase) -> dict[str, str]:
    """Digest every profile the case declares, keyed by its full identity."""
    digests = {
        f"{profile.profileId}:{profile.profileVersion}": canonical_digest_sha256(profile)
        for profile in case.paceProfiles
    }
    partner = case.equivalenceProfile
    if partner is not None:
        key = f"{partner.profileId}:{partner.profileVersion}:equivalence-source"
        digests[key] = canonical_digest_sha256(partner)
    return digests


def run_phase1_vertical_slice(
    *,
    case: Phase1E2ECase,
    output_directory: Path,
    seed: int | None = None,
) -> Phase1E2EResult:
    """Run one Phase 1 case end to end and write its canonical verification bundle."""
    effective_seed = case.seed if seed is None else seed
    bundle = Path(output_directory)
    if bundle.exists():
        shutil.rmtree(bundle)
    work = bundle / _WORK_DIRECTORY
    work.mkdir(parents=True, exist_ok=True)

    runtime_workout, source_workout_digest = _resolve_runtime_workout(case)
    workout_digest = canonical_digest_sha256(runtime_workout)
    initial_profile = case.profile_by_id(case.selectedProfileId)
    profile_digests = _profile_digests(case)
    profile_digest = profile_digests[
        f"{initial_profile.profileId}:{initial_profile.profileVersion}"
    ]
    compiled_timeline = compile_ghost_timeline(initial_profile, runtime_workout)
    timeline_digest = canonical_digest_sha256(compiled_timeline)
    scenario_digest = canonical_digest_sha256(case.scenario)
    analytics_policy_digest = canonical_digest_sha256(case.analyticsPolicy)
    replacement = case.scenario.replacementProfile

    run_id = deterministic_run_id(
        case_id=case.caseId,
        case_version=case.caseVersion,
        seed=effective_seed,
        workout_digest=workout_digest,
        source_workout_digest=source_workout_digest,
        profile_digests=profile_digests,
        selected_profile_id=initial_profile.profileId,
        selected_profile_version=initial_profile.profileVersion,
        replacement_profile_id=replacement.profileId if replacement is not None else None,
        replacement_profile_version=(
            replacement.profileVersion if replacement is not None else None
        ),
        scenario_version=case.scenario.scenarioVersion,
        scenario_digest=scenario_digest,
        analytics_policy_digest=analytics_policy_digest,
        runner_version=E2E_RUNNER_VERSION,
    )

    registry = {
        (profile.profileId, profile.profileVersion): ProfileRuntimeContext(
            profile=profile, timeline=compile_ghost_timeline(profile, runtime_workout)
        )
        for profile in case.paceProfiles
    }
    report_context = _report_context(case, run_id, registry)
    runtime_scenario = replace(case.scenario, workout=runtime_workout)

    # ---- real runtime: aggregate + journal + replay + analytics, embedded --------------
    simulation = run_scenario(
        runtime_scenario,
        work,
        seed=effective_seed,
        report_context=report_context,
    )

    equivalence_simulation: SimulationResult | None = None
    equivalence_report = None
    equivalence_work = bundle / ".equivalence-work"
    if case.equivalenceProfile is not None:
        if case.scenario.replacementProfile is not None:
            raise E2EVerificationError(
                "migration equivalence cases cannot also perform a coach profile reset"
            )
        partner = case.equivalenceProfile
        partner_timeline = compile_ghost_timeline(partner, runtime_workout)
        partner_registry = {
            (partner.profileId, partner.profileVersion): ProfileRuntimeContext(
                profile=partner, timeline=partner_timeline
            )
        }
        partner_context = replace(report_context, profileRegistry=partner_registry)
        partner_scenario = replace(
            runtime_scenario,
            profile=partner,
            replacementProfile=None,
            replacementAfterLengthIndex=None,
        )
        equivalence_simulation = run_scenario(
            partner_scenario,
            equivalence_work,
            seed=effective_seed,
            report_context=partner_context,
        )
        equivalence_report = equivalence_simulation.sessionReport

    journal_path = bundle / BUNDLE_JOURNAL_FILE
    shutil.move(str(simulation.journalPath), str(journal_path))
    shutil.rmtree(work)

    # ---- independent verification pass: re-read the journal from disk ------------------
    reread = JsonlSessionEventLog(journal_path, simulation.sessionId).read_all()
    events: tuple[EventEnvelope, ...] = reread.events
    batches = _read_batches(journal_path)
    journal_line_count = len(
        [line for line in journal_path.read_bytes().split(b"\n") if line.strip()]
    )
    replay = replay_session(events, expected_session_id=simulation.sessionId)
    replay_state = replay.state

    report = build_session_report(
        replay_state=replay_state,
        events=events,
        workout=runtime_workout,
        pace_profile=initial_profile,
        compiled_timeline=compiled_timeline,
        observations=simulation.analyticsObservations,
        report_context=report_context,
    )
    report_bytes = encode_session_report(report)
    report_sha = _sha256_bytes(report_bytes)

    warnings: list[str] = list(report.dataQuality.warningCodes)

    # ---- cross-component invariant matrix ---------------------------------------------
    checks: list[Phase1VerificationCheck] = []
    checks.extend(check_event_invariants(events, batches, journal_line_count))
    checks.extend(_rebuild_checks(simulation, report_bytes))
    checks.extend(check_state_invariants(simulation.liveFinalState, replay_state))
    checks.extend(check_clock_invariants(replay_state, case))
    checks.extend(check_distance_invariants(replay_state, runtime_workout, report))
    checks.extend(check_profile_invariants(case, replay_state, compiled_timeline, runtime_workout))
    checks.extend(check_report_invariants(report, report_bytes, events, replay_state))
    checks.extend(
        check_migration_equivalence(
            case,
            compiled_timeline,
            report,
            primary_simulation=simulation,
            partner_simulation=equivalence_simulation,
            partner_report=equivalence_report,
        )
    )
    checks.extend(
        check_expected_outcome(
            case, replay_state, report, simulation.commandOutcomes, case.paceProfiles
        )
    )

    if equivalence_work.exists():
        shutil.rmtree(equivalence_work)

    journal_bytes = journal_path.read_bytes()
    journal_sha = _sha256_bytes(journal_bytes)

    def group_ok(prefix: str) -> bool:
        return all(
            check.status is not CheckStatus.FAIL
            for check in checks
            if check.checkId.startswith(prefix)
        )

    all_passed = all(check.status is not CheckStatus.FAIL for check in checks)

    # ---- canonical payload artifacts --------------------------------------------------
    report_path = bundle / BUNDLE_REPORT_FILE
    report_path.write_bytes(report_bytes)
    outcomes_payload = [
        {
            "clientCommandId": outcome.clientCommandId,
            "commandType": outcome.commandType,
            "atMs": outcome.atMs,
            "outcome": outcome.outcome,
            "eventCount": outcome.eventCount,
            "error": outcome.error,
        }
        for outcome in simulation.commandOutcomes
    ]
    outcomes_path = bundle / BUNDLE_COMMAND_OUTCOMES_FILE
    outcomes_path.write_bytes(_canonical_json_bytes(outcomes_payload))

    observations_path: Path | None = None
    if case.emitObservations:
        observations_path = bundle / BUNDLE_OBSERVATIONS_FILE
        rendered = b"".join(
            _canonical_json_bytes(
                {
                    "timestampMs": item.timestampMs,
                    "estimatedDistanceM": item.estimatedDistanceM,
                    "smoothedVelocityMps": item.smoothedVelocityMps,
                    "phaseType": item.phaseType,
                    "quality": item.quality,
                    "trusted": item.trusted,
                    "plannedRest": item.plannedRest,
                    "source": item.source,
                }
            )
            for item in simulation.analyticsObservations
        )
        observations_path.write_bytes(rendered)

    payload_members = [
        BUNDLE_JOURNAL_FILE,
        BUNDLE_REPORT_FILE,
        BUNDLE_COMMAND_OUTCOMES_FILE,
    ]
    if observations_path is not None:
        payload_members.append(BUNDLE_OBSERVATIONS_FILE)
    artifact_digests = {
        name: _sha256_bytes((bundle / name).read_bytes()) for name in sorted(payload_members)
    }

    # The digest file intentionally excludes manifest.json to avoid a circular hash. The
    # manifest binds this file's own digest, and the file binds every payload artifact.
    digest_path = bundle / BUNDLE_SHA256_FILE
    digest_lines = [f"{artifact_digests[name]}  {name}" for name in sorted(artifact_digests)]
    digest_path.write_bytes(("\n".join(digest_lines) + "\n").encode("utf-8"))
    digest_file_sha = _sha256_bytes(digest_path.read_bytes())

    draft = Phase1VerificationManifest(
        schemaVersion=PHASE1_MANIFEST_SCHEMA_VERSION,
        manifestId="PENDING",
        manifestVersion=PHASE1_MANIFEST_VERSION,
        caseId=case.caseId,
        caseVersion=case.caseVersion,
        scenarioVersion=case.scenario.scenarioVersion,
        scenarioDigest=scenario_digest,
        analyticsPolicyDigest=analytics_policy_digest,
        runId=run_id,
        seed=effective_seed,
        workoutDigest=workout_digest,
        sourceWorkoutDigest=source_workout_digest,
        profileDigests=profile_digests,
        selectedProfileId=initial_profile.profileId,
        selectedProfileVersion=initial_profile.profileVersion,
        replacementProfileId=replacement.profileId if replacement is not None else None,
        replacementProfileVersion=(replacement.profileVersion if replacement is not None else None),
        compiledTimelineDigest=timeline_digest,
        journalSha256=journal_sha,
        reportSha256=report_sha,
        artifactDigests=artifact_digests,
        artifactDigestFileSha256=digest_file_sha,
        eventFirstSeq=events[0].seq,
        eventLastSeq=events[-1].seq,
        eventCount=len(events),
        batchCount=len(batches),
        liveReplayMatch=group_ok("state."),
        officialDistanceValid=group_ok("distance."),
        clockInvariantsValid=group_ok("clock."),
        profileInvariantsValid=group_ok("profile."),
        reportValid=group_ok("report."),
        canonicalArtifactsValid=group_ok("artifact."),
        checks=tuple(checks),
        warnings=tuple(dict.fromkeys(warnings)),
        allChecksPassed=all_passed,
        runnerVersion=E2E_RUNNER_VERSION,
        analyticsVersion=case.analyticsPolicy.analyticsVersion,
        compilerVersion=CONTINUOUS_COMPILER_VERSION,
        replayVersion=REPLAY_VERSION,
    )
    manifest = finalize_manifest(draft)
    manifest_bytes = encode_manifest(manifest)
    manifest_path = bundle / BUNDLE_MANIFEST_FILE
    manifest_path.write_bytes(manifest_bytes)

    return Phase1E2EResult(
        caseId=case.caseId,
        caseVersion=case.caseVersion,
        seed=effective_seed,
        runId=run_id,
        workoutDigest=workout_digest,
        sourceWorkoutDigest=source_workout_digest,
        profileDigest=profile_digest,
        profileDigests=profile_digests,
        scenarioDigest=scenario_digest,
        analyticsPolicyDigest=analytics_policy_digest,
        compiledTimelineDigest=timeline_digest,
        commands=tuple(outcome.clientCommandId for outcome in simulation.commandOutcomes),
        commandOutcomes=simulation.commandOutcomes,
        eventBatches=tuple(tuple(event.seq for event in batch.events) for batch in batches),
        eventCount=len(events),
        journalPath=journal_path,
        journalSha256=journal_sha,
        liveFinalState=simulation.liveFinalState,
        replayFinalState=replay_state,
        liveReplayMatch=group_ok("state."),
        sessionReport=report,
        sessionReportPath=report_path,
        sessionReportSha256=report_sha,
        verificationManifest=manifest,
        verificationManifestPath=manifest_path,
        verificationManifestSha256=_sha256_bytes(manifest_bytes),
        allChecksPassed=all_passed,
        warnings=tuple(dict.fromkeys(warnings)),
        bundleDirectory=bundle,
        commandOutcomesPath=outcomes_path,
        artifactDigestPath=digest_path,
        observationsPath=observations_path,
    )


def _rebuild_checks(
    simulation: SimulationResult, rebuilt_report_bytes: bytes
) -> list[Phase1VerificationCheck]:
    """Assert the independently rebuilt report equals the one the runtime produced."""
    same = simulation.sessionReportBytes == rebuilt_report_bytes
    return [
        Phase1VerificationCheck(
            checkId="artifact.report_rebuild_matches_runtime",
            status=CheckStatus.PASS if same else CheckStatus.FAIL,
            expected=simulation.sessionReportSha256,
            actual=_sha256_bytes(rebuilt_report_bytes),
            message="the report rebuilt from the persisted journal must be byte-identical",
        ),
        Phase1VerificationCheck(
            checkId="artifact.live_replay_match",
            status=CheckStatus.PASS if simulation.replayMatchesLiveState else CheckStatus.FAIL,
            message="the runtime harness compared live state against journal replay",
        ),
    ]


def require_all_checks_passed(result: Phase1E2EResult) -> None:
    """Raise when any cross-component invariant failed."""
    failures = [
        check for check in result.verificationManifest.checks if check.status is CheckStatus.FAIL
    ]
    if failures:
        rendered = "; ".join(
            f"{check.checkId} (expected={check.expected}, actual={check.actual})"
            for check in failures
        )
        raise E2EVerificationError(f"{result.caseId}: {len(failures)} check(s) failed: {rendered}")


__all__ = [
    "REPLAY_VERSION",
    "deterministic_run_id",
    "require_all_checks_passed",
    "run_phase1_vertical_slice",
]
