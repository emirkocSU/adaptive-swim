# IMPLEMENTATION REPORT — Adaptive Swim, Pre-Commit 7 mainline

This report documents the work performed against the Pre-Commit 7 master implementation
contract. It is evidence of what was done, not a restatement of the prompt.

## 0. Starting repository audit & packaging issue

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
