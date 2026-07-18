# Test Strategy (Phase 1)

Pyramid: unit → property → state-machine → contract → integration → e2e (headless,
network-disabled) → replay. Commits arrive in order; later layers are PENDING until their
commit.

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
