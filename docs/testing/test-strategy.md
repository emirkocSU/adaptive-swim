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
- Every rule (RULE-001 … RULE-010) has at least one valid and one invalid test, plus
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
  keywords. **Commit 4 pace math is not written yet** — Rule-009 uses an isolated estimate.
