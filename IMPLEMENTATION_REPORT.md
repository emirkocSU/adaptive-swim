# IMPLEMENTATION REPORT — Adaptive Swim, Commit 8 corrected v2

This report documents the work performed against the Phase 1 implementation contracts, in
chronological order: the pre-Commit-7 mainline repair and integration, Commit 7 (event
journal + replay), Commit 8 (continuous pace curves + headless simulator), and the **Commit
8 acceptance correction** with the ADR-039 dataset evidence plan. It is evidence of what was
done, not a restatement of the prompts.

Current state: **Commits 1–8 complete; real dataset integration corrected and validated**.
Commit 9 analytics/model training has not started.

## 0. Starting repository audit & packaging issue (pre-Commit 7)

The delivered repository tree was structurally complete for Commits 1–5 and the Commit 6
session/control implementation, but the packaged copy had **dropped several 0-byte package
files** during upload, so it did not import or run:

- `src/swimcore/time/__init__.py`, `src/swimcore/time/errors.py`, `src/swimcore/time/sim_clock.py`
- `src/swimcore/ghost/__init__.py`, `src/swimcore/ghost/errors.py`

These were reconstructed faithfully from their usages (public API, error names, `_check_time`
contract, `SimClock` monotonic semantics, ghost error taxonomy). Two example fixtures had been
duplicated from `examples/semantic_invalid/` into `examples/invalid/` (making the golden test's
structural/semantic partition inconsistent); the duplicates were removed. A `check_swimcore_purity`
name expected by the architecture test was added, the `architecture` pytest marker was
registered, and one internal contradiction between the pace-math endpoint resolver and the
compiler (direction enforcement wrongly placed in the pure math layer) was resolved by moving
the direction guard into the compiler, keeping `resolve_curve_endpoints` faithful. After this
repair the baseline was green.

## 1. Commit 6 completion / gap closure (§2)

Verified each §2 item against code and tests; the corrections group had already implemented
most invariants. Remaining true gaps closed:

- **§2.11 / §2.12** ML vs rule vs coach source handling refined: an ML request with **missing**
  confidence or data quality now abstains with distinct reasons `ML_CONFIDENCE_MISSING` /
  `DATA_QUALITY_MISSING` (previously collapsed into low-confidence). Coach-locked ML block now
  emits `COACH_PROFILE_LOCKED`. The aggregate's reason-code mapping is **exhaustive** (raises on
  any unmapped `SafetyReasonCode`, no silent default).
- **§2.11 / §2.14** the pace-target application now derives `adaptationSource` from the request
  source (`ml` / `rule_based` / `none`) instead of hard-coding `rule_based`, uses the **current
  interval target** (not `blocks[0]`), and passes profile authority fields into `SafetyContext`.
- The session/atomicity, session-id, completion, split-boundary, coach-reset ghost-anchor,
  lifecycle-pause freeze, forward-only event time, and StopPause-metadata invariants were
  confirmed present and are additionally covered by new named tests.

## 2. Distance-specific approved pace-profile mainline (§3–§14, §20, §21)

New / changed artifacts:

- **Enums (§5, §12):** `StartMode`, `WorkoutGoal`, `PaceProfileType`, `PaceProfileSource`,
  `ProfileApprovalStatus`, `PaceProfilePhase`, `HrControlMode`, `EffortTargetType`,
  `OfficialDistanceAuthority`, plus new `ReasonCode` values and pace-profile `EventType`s.
- **Workout 1.1 (§4, §6):** `WorkoutTemplateV1_1` with mandatory `StartPolicy` and
  `workoutGoal`, per-block `startMode`, `RepeatExecutionOverride`, discriminated union by
  `schemaVersion`; explicit `migrate_workout_1_0_to_1_1` (start mode never guessed).
  Start-mode resolution (`swimcore/workout/start_mode.py`): repeat → block → default.
- **ApprovedPaceProfile (§7):** `src/contracts/pace_profiles.py` — legs cover the distance
  with no gap/overlap, durations sum exactly to `targetTotalTimeSec`; leg ≠ official split.
- **Selection (§8):** `select_live_pace_profile` — deterministic authority order, coach lock,
  default-model opt-in, ambiguity raises.
- **Compiler (§9):** `compile_approved_pace_profile` — constant leg pace, bit-identical
  timeline, pool/start/stroke/coverage checks; `PaceInterval` extended with profile provenance.
- **Official-distance safety (§10):** enforced via wall-boundary split rules; wearable
  estimates cannot alter official distance or reposition the ghost.
- **Session integration (§11):** `CreateSession.paceProfileRef` runs the approved profile;
  session stores selected profile metadata, resolved start modes, pool length, goal;
  `SessionCreated`/`SessionStarted` payloads carry the metadata. Legacy 1.0 path preserved.
- **Coach lock + SafetyController (§12):** `SafetyContext` gains `profileSource`,
  `profileCoachLocked`, `currentProfileLegIndex`, `currentTargetPaceSecPer100M`.
- **Planning/profile events (§13)** and **physiology target (§14, advisory-only)** contracts.
- **External data (§15):** planning-model provenance fields and normalized-record features
  (all optional; missingness preserved; synthetic + no-eligibility rules unchanged).
- **Reporting (§20)** and **semantic rule codes (§21)** expanded.

## 3. Planning ML vs live adaptation ML (§16, §17, §18, §19)

Contract- and gate-level only. Planning model output is a DRAFT profile gated by P1–P7;
live adaptation keeps G1–G7 behind the SafetyController. Neither controls the ghost / clock /
StopPause. Personalization formula and roadmap phases documented; no real ML/UI code added.

## 4. Documentation & ADRs (§23)

Added ADR-034 (approved profiles), ADR-035 (planning ML & coach authority), ADR-036 (start
mode & official-distance authority); updated the ADR index, `CLAUDE.md` non-negotiables (11–16)
and a mainline section, `README.md`, `ARCHITECTURE.md`, `docs/domain/glossary.md`,
`docs/testing/test-strategy.md`, `docs/testing/invariants.md`, `docs/plan/phase1-commit-plan.md`
(phases + completed mainline), and `docs/data/external-data-strategy.md`.

## 5. Tests (§22)

Added: `test_workout_v1_1_schema`, `test_workout_v1_1_migration`, `test_start_mode_resolution`,
`test_approved_pace_profile_contracts`, `test_pace_profile_selection`,
`test_pace_profile_compiler`, `test_official_distance_authority`,
`test_safety_profile_authority`, `test_session_atomicity`, `test_session_split_identity`,
`test_session_current_profile_context`, `test_external_data_planning_contracts`,
`test_session_commit6_completeness`, and property invariants in
`tests/property/test_profile_and_session_invariants.py`. Example fixtures added under
`examples/valid_v1_1/` (the five required profiles + a valid 1.1 workout) and
`examples/semantic_invalid_v1_1/`.

## 6. CI results

All of the following pass on a clean tree:

```
make lint            → All checks passed!
make typecheck       → Success: no issues found in 56 source files
make schema-check    → schema-check OK (generated == committed)
make test-unit       → 445 passed
make test-architecture → 6 passed
python -m swimtools.arch_check → arch-check: OK (5 kept, 0 broken)
make ci              → CI OK
```

A standalone negative-check script confirms: wrong sessionId → `SessionIdMismatchError`;
complete before final split → rejected; 13 m split in a 25 m pool → rejected; reversed safety
bounds → rejected; ML missing confidence → abstain; workout 1.1 without start mode → rejected;
coach-authored beats model; profile total-duration mismatch → rejected; a 50 m profile cannot
be silently reused as a 25 m profile.

## 7. Remaining non-blocking notes

- The generated JSON Schemas (`workout-1.0/1.1`, `approved-pace-profile-1.0`,
  `event-envelope-1.0`, `session-report-1.0`) are committed and verified byte-identical; they
  are generator output and must not be hand-edited.
- No `.git` history was present in the working copy; the work is reported as the logical
  groups in §B rather than as separate commits.

## Final decision

**READY_FOR_COMMIT_7** — all required Commit 6 corrections and the mainline contract/core
integration are complete, with CI green. Commit 7 (append-only event log + replay) remains
intentionally out of scope.


## Commit 8 acceptance correction (ADR-039)

The acceptance review of the first Commit 8 delivery found blocking gaps. Each is closed
below; nothing in Commits 1–7 was redesigned, and the event journal, historical replay,
official-distance authority, coach authority, StopPause model, Workout 1.1 and the
deterministic runtime decisions are unchanged.

### 1. Eight required simulator scenarios (§2.1)

`src/simulator/scenarios.py` now builds exactly the eight required acceptance scenarios
under their exact slugs, each with its own workout/profile fixture:

| Slug | What it pins |
|---|---|
| `normal-pace-loss` | `baseResponseRatio = 0.90` produces a real, growing, persistent gap; ghost and ActiveClock continue; no StopPause |
| `long-stop-mid-length` | 15 s stop starting mid-length, confirmed 6 s later (retroactive freeze); mid-pool tracked alignment; exactly one wall reconciliation |
| `manual-stop-at-verified-wall` | manual coach mark at the verified 50 m wall; official-wall alignment; not a lifecycle pause |
| `duplicate-stop-mark` | identical `MarkStopPause` twice → zero new events, one open interval, one journal batch |
| `stop-during-planned-rest` | schedule-level rest; no StopPause; stopped duration stays 0; no synthetic core state |
| `unreliable-position-time` | LOW position confidence window; estimate stays visual; official distance unchanged |
| `complete-while-stop-paused` | `CompleteSession` rejected while open (journal untouched), succeeds after resolve |
| `coach-continuous-curve-reset` | mid-length request, next-wall apply, full metadata swap, split history preserved |

The former demo scenarios remain as helper examples; the alias table that mapped
`normal-pace-loss → even-on-plan`, `long-stop-mid-length → stop-pause` and
`coach-continuous-curve-reset → coach-continuous-reset` was **deleted**, and a test asserts
the old alias names no longer resolve.

### 2. Real seed plumbing (§2.2)

`--seed` is passed into `run_scenario(..., seed=...)` and reaches the virtual swimmer's
instance-local splitmix64 PRNG. The scenario registry default is used when no override is
given. No `random.seed()` anywhere. Verified: same scenario + same seed → identical journal
SHA-256 *and* identical observation trace; a different seed changes the trace while all
domain invariants still hold.

### 3. Tick-based VirtualSwimmer (§2.3)

`VirtualSwimmerConfig(seed, tickMs=100, baseResponseRatio, fatigueSlopePer100M, noiseStdMps,
minimumActualSpeedMps, maximumActualSpeedMps, turnDelayMs)` drives a manual sim clock. Each
tick emits an immutable `SwimmerObservation` (wall time, active time, actual distance/speed,
target distance/speed, gap, phase type, position quality, planned-rest flag). Actual motion
= target envelope × deterministic response + fatigue trend + seeded bounded Gaussian noise
(Box–Muller over the same PRNG) + scenario injection. Targets come from **real** swimcore
queries; official wall crossings are found by deterministic interpolation inside the
crossing tick. No `time.sleep`, no wall-clock time, no I/O.

### 4. Complete harness result and internal replay validation (§2.4)

`SimulationResult` now carries `scenarioId`, `scenarioVersion`, `seed`, `runId`, `manifest`,
`commands`, `commandOutcomes`, `events`, `eventBatches`, `observations`, `ghostSnapshots`,
`journalPath`, `journalSha256`, `liveFinalState`, `replayResult` and
`replayMatchesLiveState`. At the end of every run the harness re-reads its own journal,
flattens the events, calls `replay_session`, and compares every comparable field of live
and replay state; a mismatch raises `SimulationError` and fails the run. This is part of the
harness acceptance, not left to a test file.

### 5. Safe-wall reset metadata (§2.5)

A continuous-curve replacement now updates **all** selected-profile state:
`selectedPaceProfileId`, `Version`, `Source`, `Type`, `profileCoachLocked`,
`appliedPaceSecPer100M` (computed from the replacement timeline's current target just after
the wall), `targetTotalTimeSec`, `curveRepresentation` and `curveCompilerVersion`. The
fields were added as optional, backward-compatible entries to `PendingCoachReset`,
`CoachPacingResetRequestedPayload`, `CoachPacingResetAppliedPayload`, `SessionCreatedPayload`,
the aggregate state, `HistoricalSessionState` and the replay reducer. Old journals still
parse; a `COACH_AUTHORED` source does not survive a `COACH_APPROVED_MODEL` replacement; a
coach-locked replacement reads as locked in live *and* replay state; the swap stays atomic.

### 6. Post-reconciliation physical bounds (§2.6)

The compiler's `_reconcile` now returns the per-span pace scale factors, and every supplied
bound — minimum/maximum speed, maximum acceleration, maximum deceleration, maximum speed
gradient — is re-verified after reconciliation at each region's scale. A breach raises
`ProfileCompilationError` (reject, never clamp), and `physicalBoundsChecked = true` is
written only when that post-check actually passed.

### 7. Analytic spline critical points (§2.7)

`swimcore/pacing/curve_bounds.py` treats each PCHIP interval as a cubic in local `t`:
speed extrema are the closed-form roots of `v'(t) = 0`, gradient extrema come from
`v''(t) = 0` plus endpoints, and acceleration `a = v · dv/dd` is verified by branch and
bound with the mathematically valid per-subinterval bound `|a| ≤ max|v| · max|dv/dd|`
computed from those closed-form extrema. Subintervals certified by the bound need no
pointwise evaluation; only subintervals that could breach are split further. Sampling on the
0.10 m breakpoint grid is retained as additional corroboration, never as proof. A test
constructs a violation that sits between grid points and asserts it is caught.

### 8. Finite validation at the contract boundary (§2.8)

`contracts/_base.py` adds `FiniteFloat`, `PosFiniteFloat`, `NonNegFiniteFloat` and
`UnitFiniteRatio` (`allow_inf_nan=False`). Curve knots, constant-speed segments, phases,
target-time and split-time constraints, the validation summary and the profile total
distance now use them, so `+inf` no longer satisfies a "positive" constraint and `NaN` is
rejected at parse time.

### 9. Simulator provenance (§2.9)

`SimulationRunManifest` carries `synthetic = true`, scenario id/version, seed, simulator and
harness versions, workout ref, profile id/version, curve representation, compiler version
and `runId = sha256(scenarioId + scenarioVersion + seed + workoutRef + profileId +
profileVersion)`. No timestamp, no UUID. Synthetic output is never marked as production
performance evidence.

### 10. Dataset catalog, validator, gates and guards (§3–§7, §11, §12)

- `contracts/data_assets.py` — `DatasetAssetManifest`, `DatasetFileManifest`,
  `DatasetRestriction`, `DatasetValidationSummary`, `ProductionViewRequest`, with the
  license, quarantine, override and ground-truth rules enforced in validators.
- `contracts/forecasting.py` — `RepeatForecastContext` / `RepeatForecastOutput`, keeping
  coach target and model forecast separate and forbidding `BOUNDED_AUTO` under OOD or
  domain extrapolation.
- `data/catalog/*.json` — five checked-in manifests (four primary bundles plus the
  quarantined stroke file alias) recording exact supplied ZIP/member hashes, row/column
  counts, real raw required headers, normalized mappings, roles, licenses, eligibility,
  restrictions, grouping keys, leakage rules and QA warnings.
- `data/schemas/*.json` — per-dataset expectations; `data/external/raw/` is gitignored.
- `swimtools/data_catalog.py` — typed loading, raw-to-canonical normalization, primary
  bundle de-duplication and bundle/file-level eligibility gates raising
  `DatasetEligibilityError`.
- `swimtools/validate_dataset_bundle.py` — stdlib-only streaming validator (`zipfile`,
  `csv`, `hashlib`) with bounded memory, single-pass hashing, real raw-header and
  granularity checks, multi-file bundle support, and rejection of zip-slip paths,
  duplicate members, unexpected members and missing members.
- `swimtools/data_splitting.py` — pure leakage validators for race, athlete, trial,
  pre/post, crossover and time-series grouping, time-aware splits and feature allowlists.
- `swimtools/swimming_features.py` — `cumulative_time_share`, `race_average_speed_mps`,
  `segment_speed_ratio_to_race_average`, `target_intensity_ratio`,
  `softmax_normalized_training_distribution`, `time_density_scale_factor`.

### 11. Evidence provenance and roadmap (§8–§10, §13)

New enums (`CurveOrigin`, `CurveEvidenceLevel`, `VisualShapeSource`, dataset and forecast
enums) and an additive `CurveProvenance` extension record how a curve was produced and how
much evidence stands behind its shape. A coarse-split-derived or bounded-template curve
cannot claim `continuousCurveGroundTruth`. ADR-039 was written and ADR-038's scope was
clarified (its transformer is a long-term target, not the active architecture); the
`normal-pace-loss` fixture profile carries the new provenance; `docs/plan/model-roadmap.md`
sequences Phase 5A–5E with mandatory baselines. `src/ml/` is not created.

### 12. Real dataset validation — PERFORMED

The four supplied raw ZIP bundles were validated directly with the repository CLI. No raw
ZIP/CSV was copied into the repository. Results:

| Bundle | Result | Rows × columns / members | Effective role and gate |
|---|---|---|---|
| Official race | VALID | 128,475 × 151 | `RACE_PACING_PRIOR`; `LICENSE_BLOCKED`; continuous curve ground truth false |
| IMU | VALID | 40,957 × 94 | sensor encoder/technique research; not primary pacing target; not official distance |
| Training/fatigue | VALID | 396 × 111 | 228 `ATHLETE_WEEK` + 168 `SPRINT_REPEAT` counted from real `record_granularity`; mixed license |
| External studies | VALID | seven exact members | controlled studies research eligible; massage condition-aware advisory; stroke member `SMOKE_TEST_ONLY` |

Exact bundle/member SHA-256 values, row/column counts and raw required headers are now
recorded in `data/catalog/*.json`. The previous false raw requirements (`subject_uid`,
`session_uid`, `record_type`) were removed from sources that do not contain them. Canonical
views use explicit mappings:

```text
source_participant_id -> subject_uid
session_or_trial_id   -> session_uid
record_granularity    -> record_type
```

The external stroke CSV remains inside the external-studies ZIP. The primary bundle manifest
validates the ZIP once; the separate stroke catalog record has `validationPrimary=false` and
exists only as a file-level eligibility alias.

### 13. Tests and CI regression evidence

Completed in this execution environment:

- the four requested `python -m swimtools.validate_dataset_bundle --bundle ...` commands:
  **4 VALID**;
- `python -m swimtools.validate_dataset_bundle --all --data-root /mnt/data`: **4 primary
  bundles, all VALID**; the non-primary stroke alias was not run as a second bundle;
- dataset/catalog validator unit tests: **32 passed**;
- unit suite excluding the three legacy unit files that import unavailable Hypothesis:
  **589 passed, 3 skipped**;
- replay suite without the unavailable `pytest-socket` CLI option: **131 passed**;
- simulator suite without the unavailable `pytest-socket` CLI option: **109 passed**;
- architecture tests excluding the one subprocess test that invokes unavailable
  `lint-imports`: **30 passed**;
- generated schema check: **OK**;
- Python compile/import checks: **OK**;
- byte-for-byte comparison with the supplied corrected full repository: `src/swimcore`,
  `src/simulator`, `src/persistence`, `tests/replay` and `tests/simulator` are unchanged.

The exact requested command matrix was also attempted. The execution image does not provide
`ruff`, `mypy`, `lint-imports`, `hypothesis` or `pytest-socket`, and package installation is
unavailable in this sandbox. Consequently:

| Requested command | Result in this sandbox |
|---|---|
| `ruff check src tests` | not executable: `ruff` missing |
| `ruff format --check src tests` | not executable: `ruff` missing |
| `mypy --strict src` | not executable: `mypy` missing |
| `lint-imports` | not executable: `lint-imports` missing |
| `python -m swimtools.arch_check` | purity/path scan reached the external `lint-imports` step, then stopped because the executable is missing |
| `python -m swimtools.gen_schemas --check` | **PASS** |
| `pytest -q tests/unit` | collection blocked only by three files importing missing Hypothesis; remaining suite **589 passed, 3 skipped** |
| `pytest -q tests/property` | collection blocked by missing Hypothesis |
| `pytest -q tests/replay --disable-socket` | `pytest-socket` option unavailable; same suite without the option **131 passed** |
| `pytest -q tests/simulator --disable-socket` | `pytest-socket` option unavailable; same suite without the option **109 passed** |
| `pytest -q tests/architecture` | one failure because its subprocess could not find `lint-imports`; remaining **30 passed** |
| `make ci` | stops at the first `ruff` invocation because `ruff` is missing |

The supplied corrected baseline report records the complete Commit-8 `make ci` as green.
This correction changes only dataset contracts/catalog/schema/validator/tests/docs, while the
simulator/core/replay implementation and their regression fixtures remain byte-identical and
their directly runnable suites remain green.

### 14. Final decision

`READY_FOR_COMMIT_9`
