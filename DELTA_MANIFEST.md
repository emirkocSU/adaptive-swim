# DELTA MANIFEST — Adaptive Swim Phase 1 Final Correction

**Base:** `adaptive-swim-phase1-complete-full.zip`
**Delta archive:** `adaptive-swim-commit10-delta.zip`
**Tests executed by packager:** none; operator validation required

## Corrected blockers

- Atomic rollback preserves aggregate values and the original ActiveClock/GhostClock/PaceTimeline reference graph.
- Simulator live state reads the aggregate ActiveClock rather than a GhostClock workaround.
- E2E and simulator run identities cover source/runtime workout, scenario digest, all profile digests, replacement profile, analytics policy and component version.
- The byte verifier recomputes runId, reportId and manifestId.
- The manifest binds command outcomes, optional observations, journal, report and the canonical digest file.
- Migration equivalence executes two complete aggregate/journal/replay/report chains.
- The legacy compatibility case starts from a real Workout 1.0 source.
- Mechanical Phase 1 completeness and a real Makefile target replace every temporary-success path.
- Duplicate pytest markers and stale historical status/deferred text are removed or explicitly labelled.
- Analytics and E2E golden reports/bundles are regenerated under the expanded run identity and manifest 1.1 contract.

## Added (13)

- `src/e2e/identity.py`
- `src/swimtools/completeness_check.py`
- `tests/architecture/test_phase1_completeness.py`
- `tests/e2e/goldens/coach-reset/artifact-sha256.txt`
- `tests/e2e/goldens/coach-reset/command-outcomes.json`
- `tests/e2e/goldens/dataset-evidence/artifact-sha256.txt`
- `tests/e2e/goldens/dataset-evidence/command-outcomes.json`
- `tests/e2e/goldens/legacy-profile/artifact-sha256.txt`
- `tests/e2e/goldens/legacy-profile/command-outcomes.json`
- `tests/e2e/goldens/long-stop/artifact-sha256.txt`
- `tests/e2e/goldens/long-stop/command-outcomes.json`
- `tests/e2e/goldens/normal-continuous/artifact-sha256.txt`
- `tests/e2e/goldens/normal-continuous/command-outcomes.json`

## Changed (47)

- `CLAUDE.md`
- `DELTA_MANIFEST.md`
- `IMPLEMENTATION_REPORT.md`
- `Makefile`
- `PHASE1_RELEASE_MANIFEST.json`
- `README.md`
- `docs/adr/ADR-041-phase1-vertical-slice-verification-and-release-closure.md`
- `docs/plan/deferred-map.md`
- `docs/plan/first-10-commits.md`
- `docs/plan/phase1-commit-plan.md`
- `docs/testing/invariants.md`
- `docs/testing/phase1-completeness.md`
- `docs/testing/test-strategy.md`
- `pyproject.toml`
- `src/analytics/identity.py`
- `src/e2e/cases.py`
- `src/e2e/manifest.py`
- `src/e2e/runner.py`
- `src/e2e/types.py`
- `src/e2e/verification.py`
- `src/simulator/harness.py`
- `src/simulator/provenance.py`
- `src/swimcore/ghost/clock.py`
- `src/swimcore/session/aggregate.py`
- `src/swimtools/verify_e2e_bundle.py`
- `tests/analytics/goldens/coach-curve-reset-report.json`
- `tests/analytics/goldens/long-stop-report.json`
- `tests/analytics/goldens/normal-pace-loss-report.json`
- `tests/e2e/goldens/coach-reset/manifest.json`
- `tests/e2e/goldens/coach-reset/session-report.json`
- `tests/e2e/goldens/dataset-evidence/manifest.json`
- `tests/e2e/goldens/dataset-evidence/session-report.json`
- `tests/e2e/goldens/legacy-profile/manifest.json`
- `tests/e2e/goldens/legacy-profile/session-report.json`
- `tests/e2e/goldens/long-stop/manifest.json`
- `tests/e2e/goldens/long-stop/session-report.json`
- `tests/e2e/goldens/normal-continuous/manifest.json`
- `tests/e2e/goldens/normal-continuous/session-report.json`
- `tests/e2e/test_e2e_bundle_verifier.py`
- `tests/e2e/test_e2e_determinism.py`
- `tests/e2e/test_e2e_manifest.py`
- `tests/e2e/test_golden_artifacts.py`
- `tests/e2e/test_phase1_case_matrix.py`
- `tests/property/test_e2e_determinism.py`
- `tests/simulator/test_scenarios.py`
- `tests/simulator/test_virtual_swimmer.py`
- `tests/unit/test_session_atomicity.py`

## Removed (5)

- `tests/e2e/goldens/coach-reset/sha256.txt`
- `tests/e2e/goldens/dataset-evidence/sha256.txt`
- `tests/e2e/goldens/legacy-profile/sha256.txt`
- `tests/e2e/goldens/long-stop/sha256.txt`
- `tests/e2e/goldens/normal-continuous/sha256.txt`

The delta ZIP includes `DELTA_DELETE_PATHS.txt`; delete those paths before overlaying the delta on the base repository.

## Version changes

```text
e2e-runner-1.1.0
phase1-verification-1.1.0 / schema 1.1
sim-harness-2.1.0
sim-transform-1.1.0
Phase 1 release 1.1.0
```

## Validation note

No pytest, Ruff, Mypy, import-linter, schema-check, simulator-test or CI command was run for this correction delivery. The committed tests and completeness gate are supplied for the operator to execute after extraction.

## Archive exclusions

The full and delta archives exclude `.git`, virtual environments, caches, bytecode, build/dist output, temporary E2E output and raw external dataset ZIP/CSV files.
