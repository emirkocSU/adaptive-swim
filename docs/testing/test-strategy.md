# Test Strategy (Phase 1)

Pyramid: unit → property → state-machine → contract → integration → e2e (headless,
network-disabled) → replay. All Phase 1 layers now have real targets; the Makefile contains
no temporary-success or `PENDING` fallback.

## Commit 2 (this commit) — contracts & schema

- Valid golden workouts pass the generated JSON Schema.
- Schema-level invalid examples are rejected by the JSON Schema; semantic-level invalid
  examples are structurally valid and deferred to the Commit 3 semantic validator.
- `make schema-check`: generated schemas match the committed files byte-for-byte.
- JSON Schema uses only standard draft 2020-12 keywords (no custom keywords).
- `minPace` / `maxPace` / `coachMinPace` / `coachMaxPace` appear nowhere.
- No general `IncidentStarted` / `IncidentResolved` event names; StopPause terminology is
  used. `MANUAL_INCIDENT` survives only as a StopPause trigger.
- `activeDurationSec` / `stoppedDurationSec` / `elapsedDurationSec` are on the
  length/report contracts.
- `performanceRelatedStopProbability` is an optional advisory field on the efficiency
  contract; it controls nothing.
- External records cannot merge without `data_domain`; no production-eligibility flag;
  synthetic records carry provenance + `synthetic=true`.

## Ghost / StopPause behaviour (contract-level in Commit 2, logic in later commits)

Three behaviours must stay distinct: normal/large pace loss (ghost ACTIVE), coach pacing
reset (new reference at wall), StopPause (clock frozen, ghost aligns to swimmer, reconcile
at wall). During a **verified** StopPause, controlled mid-pool ghost alignment is allowed;
unverified or normal pace loss must not reposition the ghost mid-length.

## Commit 3 (this commit) — semantic workout validator

- The validator lives in `swimcore/workout/` and is **pure**: `test_validator_performs_no_io`
  patches `open` to prove no filesystem access, and the import-linter contract keeps
  `swimcore` free of I/O frameworks and `contracts.external_data`.
- Every rule (RULE-001 … RULE-012) has at least one valid and one invalid test, plus
  boundary tests where relevant (e.g. segment boundary WARNING vs strict ERROR).
- `src/contracts/examples/semantic_invalid/` holds structurally-valid, semantically-invalid
  goldens — kept **separate** from the schema-level `examples/invalid/` set. Each is
  cross-checked against its expected rule code.
- Result semantics are tested directly: warnings do not invalidate, errors do, issues are
  deduplicated, ordering is deterministic ((block, segment, rule)), and the input is never
  mutated.
- Context behaviour is tested: a missing context degrades reference rules to
  `REFERENCE_NOT_VERIFIED` (WARNING); a supplied context turns an unknown reference into
  `REFERENCE_NOT_FOUND` (ERROR). Migration registry exposes only the `1.0 → 1.0` no-op.
- JSON Schema remains structural-only; semantic defects are never encoded as schema
  keywords. Rule-009 shares the single Commit-4 pace formula (no second estimate).

## Commit 4 (this commit) — deterministic pace math

- `swimcore/pacing/` is pure: covered by the `arch_check` AST purity scan (no
  `open`/`eval`/`exec`/I/O/network/db/framework) plus import-linter (imports `contracts` +
  stdlib only). `make ci` now runs `python -m swimtools.arch_check`.
- Unit files by mode: `test_pace_math_even`, `_controlled_start`, `_progressive`,
  `_negative_split`, `_timeline`; property invariants in `test_pace_math_properties`
  (Hypothesis): round-trips, monotonicity, timeline totals, pace within endpoint range,
  wall multiples, NaN/inf rejected.
- Verified numerics: `100 m @ 80 = 80 s`, `50 m @ 80 = 40 s`, `10×100 timeline = 1000 m`,
  rest excluded from active timeline, progressive distance/time round-trip, negative-split
  ordering, deterministic bit-identical repeated calls.
- New semantic rules (RULE-011 controlled start, RULE-012 negative-split order) have valid +
  invalid tests and semantic-invalid goldens; the `controlled_start` valid golden exercises
  the new optional `startPaceSecPer100M` schema field.

## Commit 5 (this commit) — deterministic clocks & ghost primitive

- `swimcore/time/` and `swimcore/ghost/` are pure — covered by the `arch_check` AST scan
  (no `time.time()`/`datetime.now()`/`sleep`/I/O) and import-linter (imports `contracts` +
  `swimcore` + stdlib only).
- Files: `test_sim_clock` (explicit init, deterministic/zero/negative advance, backward-set
  reject, identical repeated sequence), `test_active_clock` (active-before-pause, retroactive
  freeze, fixed-during-pause, resume, multiple intervals, all invalid transitions),
  `test_ghost_clock_progression` (0→0, even/progressive/controlled-start, total→total, normal
  pace loss = no alignment, snapshot purity), `test_ghost_clock_stop_pause` (retro freeze,
  align to tracked point, fixed during pause, resume from aligned, unchanged timeline/pace, no
  jump back, multiple intervals, alignment at 0 / near final / <0 / >total / NaN-inf),
  `test_ghost_clock_alignment` (25 m & 50 m walls, non-wall/beyond-total/backward rejected,
  timeline untouched, alignment cleared), `test_ghost_clock_properties` (Hypothesis: clock
  monotonic, active ≤ wall, stopped = wall − active, display constant while paused, display
  monotonic/bounded while active, timeline independent of alignment offset, identical
  snapshots for identical inputs).
- Acceptance verified: a stop starting at 10 s and confirmed at 20 s freezes the active clock
  at 10 s; the ghost does not move during the pause; resume continues from the aligned
  position with the same target-pace context; normal pace loss produces no alignment; wall
  reconciliation only accepts a valid wall; identical SimClock sequences are bit-identical.

## Commit 4 & 5 fixes (this pass)

- Curve helpers (`curve_duration`, `elapsed_at_local_distance`, `pace_at_local_distance`,
  `local_distance_at_elapsed`) reject NaN/±inf and out-of-range length/distance/time/pace with
  domain errors; the previously misnamed timeline test is renamed
  `test_timeline_queries_reject_nan_and_infinity` and dedicated
  `test_*_rejects_non_finite_values` curve tests were added.
- Wall helpers guard finite pool/distance/total, `distance <= total`, forward-only
  `next_wall_boundary`, and raise `InvalidPoolLengthError` for bad pool lengths.
- `ActiveClock` is now a monotonic runtime primitive: historical snapshot/query rejected,
  resume must be `>= confirmation`, multiple stops supported, and invariants
  (`0 <= active <= wall`, `stopped >= 0`, `wall = active + stopped`, monotonic transitions)
  are covered by unit + Hypothesis tests.
- `GhostClock` reconciles a pending alignment exactly once, only at the expected next valid
  wall (pool 25 / alignment 48 ⇒ only 50 accepted; 75/100 rejected), validates pool length /
  timeline total at construction, and rejects historical snapshots and reconciliation without
  a pending alignment.

## Follow-up fixes (forward-only clock, finite results, wall totals)

- ActiveClock is forward-only by observation: `test_snapshot_cannot_move_backward_without_transition`,
  `test_freeze_confirmation_cannot_precede_last_observed_time`,
  `test_ghost_stop_pause_cannot_rewind_after_later_snapshot`.
- Pace math never returns non-finite even for huge finite inputs
  (`test_large_finite_inputs_do_not_return_infinity`, `test_curve_duration_overflow_is_rejected`).
- `next_wall_boundary` never returns a non-wall final distance
  (`test_next_wall_rejects_non_wall_total_distance`); GhostClock rejects a non-wall timeline
  total (`test_constructor_rejects_non_wall_total_distance`).

## Commit 6 (this commit) — session orchestration & SafetyController

- `swimcore/session/` and `swimcore/control/` are pure (arch_check AST scan + import-linter;
  a new contract forbids `control` depending on `session`).
- Files: `test_session_lifecycle` (transitions, invalid transitions, terminal rejects),
  `test_session_command_idempotency` (duplicate no-op, conflict, monotonic seq),
  `test_session_stop_pause` (RUNNING during StopPause, retroactive correction, ghost
  STOP_PAUSED, resolve, interval mismatch, second-open/overlap rejected, split reconciles /
  wrong-wall rejected), `test_session_splits` (record/verify, ordering, duplicates,
  missing-verify, StopPause does not INVALID a split), `test_session_coach_pacing_reset`
  (no clock stop, not mid-length, applied at next wall, conflicting pending rejected,
  requested+applied events, prior splits preserved), `test_safety_controller` (all gates,
  bounds, reason codes, smaller=faster, heart-rate-only reject, determinism),
  `test_session_properties` (Hypothesis: seq increasing, terminal never transitions, identical
  sequences → identical events, duplicates no-op, applied pace within bounds, active+stopped=
  wall, RUNNING during StopPause) plus atomicity (failed command unchanged, failed alignment
  doesn't freeze the clock, failed pace decision doesn't change target, failed reconciliation
  leaves pending intact).

## Mainline (approved pace profiles) test strategy

- **Workout 1.1 / start mode:** schema requiredness, explicit migration (no guessed start
  mode), and resolution precedence (`test_workout_v1_1_schema`, `test_workout_v1_1_migration`,
  `test_start_mode_resolution`).
- **Pace profiles:** exact-distance coverage, exact target-time reconciliation, authority
  order, coach lock, default-model opt-in, 25 m vs 50 m mismatch, leg-vs-official-split
  distinction, sprint positive split, negative split
  (`test_approved_pace_profile_contracts`, `test_pace_profile_selection`,
  `test_pace_profile_compiler`).
- **Sensor-distance safety:** estimated distance cannot alter official split/total, a normal
  dive cannot reposition the ghost, StopPause alignment is visual/temporary
  (`test_official_distance_authority`).
- **Safety profile authority:** ML missing confidence/quality → distinct abstain reasons,
  coach-locked profile blocks ML auto-apply, current-interval bounds
  (`test_safety_profile_authority`, `test_session_current_profile_context`).
- **Property invariants:** deterministic selection respecting priority; compiled duration
  equals profile total; official distance is a pool-length multiple
  (`tests/property/test_profile_and_session_invariants`).

## Commit 7 — append-only event journal + deterministic replay

- One command = one `EventBatchRecord` = one canonical JSONL line; contract tests reject
  empty/mixed/discontinuous/duplicate batches.
- Codec tests: byte-identical re-encoding, exactly one LF, sorted compact JSON,
  NaN/Infinity rejection (encode + decode), unknown recordVersion, blank/BOM lines, and
  wrapped (never raw) JSON/Unicode/Pydantic errors.
- Journal tests: append creates + fsyncs (file and, on creation, parent dir), partial
  `os.write` and EINTR handled, session/seq/timestamp/eventId validation, order preserved.
- Retry tests: exact duplicate → `ALREADY_PRESENT` without a second line; same
  seq/commandId with different content and partial overlaps conflict; injected fsync
  failure → `EventLogDurabilityUncertainError`, safe re-fsync retry (§26 adversarial).
- Tail recovery tests: valid log untouched; valid-but-unterminated final record retained
  (repair adds only `\n`); torn tail truncated with exact byte-count notice; repair is
  idempotent; middle corruption and newline-terminated invalid final lines are
  `CorruptEventLogError` (never skipped); blank lines rejected.
- Replay tests: lifecycle (incl. §26 pause example), retroactive StopPause (§26 numbers:
  wall 35 s / stopped 25 s / active 10 s), open stop at horizon, overlap/mismatch
  rejection, splits + verification, official distance from pool geometry (wearable source
  never rewrites it), coach reset (not a StopPause; splits preserved), pace target and
  control-decision reason preservation, profile metadata, stream validation (§17), and
  `SessionRecovered` semantics (§18).
- Golden replay journals (`tests/replay/goldens/`): committed bytes equal the
  deterministically regenerated ones; the same history in two directories is sha256-equal.
- Property tests (Hypothesis): codec round-trip byte identity; contiguous flattened seq;
  read order == append order; duplicate appends never grow the file; tail repair never
  touches bytes before the last complete newline; duration invariants
  (`elapsed = active + stopped`, `wall = elapsed + lifecyclePaused`, all >= 0);
  non-overlapping completed StopPauses; pool-multiple official distance; replay never
  mutates its input.
- Architecture tests: `swimcore.replay` imports no persistence/filesystem/time/randomness/
  uuid and no `ActiveClock`/`GhostClock`/`SessionAggregate`; `persistence` uses no
  SQLite/web/network; `swimcore` never imports `persistence`; the layered import-linter
  contract is unchanged.

## Commit 8 — continuous pace curves + deterministic simulator (ADR-038)

- Contract tests: 1.1 profile validation (knots, phases, locked splits, pool alignment,
  coach-lock), 5 valid fixtures load, 12 invalid fixtures reject.
- PCHIP: exact knot interpolation, no adjacent-value overshoot, determinism, degenerate-input
  rejection, finite derivative.
- Compiler: exact total-time and locked-split reconciliation, distance↔time inverse
  round-trip, bit-identical compilation, physical-bounds accept/reject (incl.
  post-reconciliation), compiler-authoritative summary.
- Migration: non-mutating, timeline-preserving (Demonstration B), provenance, 25/50 m pools,
  pool-mismatch rejection.
- Session integration: 1.1 profile drives create→arm→start; profile-selection authority;
  default-model opt-in; official distance from geometry; normal pace loss is not a StopPause.
- Coach continuous-curve reset: applies at the next wall, swaps profile, not a StopPause,
  atomic rejection on unknown/mismatched replacement.
- Feature extraction: pure, deterministic, rejects NaN/inf/zero-denominator/negative.
- External-data + report: optional continuous fields accepted, missingness preserved,
  synthetic-domain rule intact, `ContinuousCurveReportContext` optional.
- Property: curve invariants (deterministic, exact total, positive speeds, round-trip,
  no-mutation) and simulator determinism (byte-identical journals, synthetic provenance).
- Simulator: all 8 scenarios reach COMPLETED via the real core, live↔replay agree, official
  distance is a pool multiple, StopPause/coach-reset scenarios behave correctly, 3 committed
  goldens match, CLI list/run/alias/hash.
- Architecture: the simulator redefines no core type, PCHIP is defined once, no
  network/sleep/sqlite, swimcore imports neither simulator nor persistence nor external_data.


## Commit 8 correction additions (ADR-039)

- **Simulator regression** (`tests/simulator/`): the eight required scenarios exist under
  their exact slugs and are not aliases; `normal-pace-loss` produces a real, persistent gap;
  the CLI seed changes the real simulation while the same seed reproduces byte-identical
  journals and observation traces; the harness validates live state against a re-read
  journal replay; replacement-profile metadata is asserted in live *and* replay state;
  simulation provenance and the deterministic `runId` are complete.
- **Bounds** (`tests/unit/test_post_reconciliation_bounds.py`,
  `test_curve_evidence_and_bounds.py`): post-reconciliation speed, gradient and acceleration
  bounds; per-region scales for locked splits; a violation hidden *between* sampling points
  is caught; `physicalBoundsChecked` only set after the post-check passes.
- **Finite contracts**: `+inf`, `-inf` and `NaN` rejected on curve knots, targets,
  tolerances and confidences.
- **Dataset catalog** (`tests/unit/test_dataset_catalog.py`): manifests parse; hash, row,
  column and required-column mismatches are rejected; unexpected members, zip-slip paths and
  missing members are rejected; the license gate and the quarantine gate deny production
  views; a large CSV is streamed with bounded memory. CI fixtures are tiny representative
  bundles built in-process — the real multi-hundred-megabyte bundles are validated out of
  band with `python -m swimtools.validate_dataset_bundle --all --data-root ...`.
- **Leakage** (`tests/unit/test_data_leakage_guards.py`): race, athlete, trial, pre/post,
  first/second-25, crossover and time-series grouping violations plus lookahead splits and
  forecast-label features are all rejected.
- **Provenance** (`tests/unit/test_curve_evidence_and_bounds.py`): a coarse-split-derived or
  bounded-template curve cannot claim ground truth; target and forecast fields stay
  separate; `BOUNDED_AUTO` is forbidden under OOD/extrapolation; synthetic simulator data is
  never external evidence.
- **Architecture** (`tests/architecture/test_dataset_boundaries.py`): swimcore reads no
  dataset, contracts do no I/O, the simulator imports no dataset tooling, `src/ml/` does not
  exist, no runtime pandas/numpy, and no raw CSV/ZIP is committed under `data/` or `src/`.

## Commit 9 analytics test layer

`tests/analytics` runs replay-to-report integration, the eight required simulator report
acceptance cases, builder/verifier CLI smoke tests and canonical golden JSON files. Unit
tests cover contracts, identity, timing, distance, splits, pacing/fade, trusted curve gates,
StopPause, sensors, quality, provenance, serialization and the atomic report store. Property
tests cover deterministic identity/bytes, roundtrip and split metric ranges. Architecture
tests reject analytics I/O, randomness, network/ML dependencies and reverse imports.

`tests/analytics/test_report_blocker_regressions.py` permanently covers the corrected Commit 9
blockers: reset-profile CLI registry, content-addressed identity under observation/policy changes,
fixed schema version, workout/profile/timeline coherence, session-horizon observation rejection,
smoothed-velocity-only integration, pending wall reconciliation, planned-rest quality denominator,
canonical report-store enforcement and nullable directional extrema.


## Commit 10 — Phase 1 vertical-slice suite (ADR-041)

`tests/e2e/` runs the whole chain with real components. A session-scoped fixture executes
each case once and caches the result, because one case drives aggregate + journal + replay +
analytics end to end.

| File | Covers |
|---|---|
| `test_phase1_vertical_slice.py` | one slice end to end: bundle members, journal-as-authority, geometry, report content, no path leakage |
| `test_phase1_case_matrix.py` | all thirteen cases pass every check; per-case expectations for cases 1–10 |
| `test_cross_component_invariants.py` | every invariant group present; live/replay/report agreement; clock, distance and report invariants |
| `test_e2e_determinism.py` | same case+seed ⇒ identical bytes; output path irrelevant; seed sensitivity; pure run identity |
| `test_e2e_manifest.py` | manifest field completeness, canonical JSON, content-addressed id, group flags, no environment values |
| `test_e2e_bundle_verifier.py` | pristine bundle valid; missing file, one changed byte, pretty JSON, tampered digest and semantic disagreement all rejected with typed exit codes |
| `test_e2e_cli.py` | `--list`, invalid input, JSON/text output, run→verify round trip |
| `test_backward_compatibility_matrix.py` | every supported schema still committed; workout 1.0 fixtures still parse and migrate; profile 1.0 runs unmigrated; envelope/batch stay 1.0; report 1.1 is current; no 2.0 bump |
| `test_failure_atomicity.py` | rejected command persists nothing; duplicate retry changes nothing; corrupt middle journal rejected; no network; missing observations never fabricate metrics |
| `test_golden_artifacts.py` | committed golden bundles reproduced byte for byte, digests match, no environment content |
| `tests/property/test_e2e_determinism.py` | Hypothesis: identical artifacts for a case+seed; run id is a pure hash |
| `tests/property/test_e2e_state_equivalence.py` | Hypothesis: live == replay == report; distance and duration invariants; no raw dataset path in any artifact |
| `tests/architecture/test_e2e_boundaries.py` | inner layers never import e2e; no forbidden imports; no sleep/wall clock; no duplicated domain logic; layer order |

`make test-e2e` runs the suite. `make e2e-headless` runs the real CLIs over the full matrix
and then verifies every emitted bundle byte by byte. Both are part of `make ci`.
