# ADR-040 — Deterministic Session Analytics and Derived Reports

**Status:** ACTIVE — corrected Commit 9
**Date:** 2026-07-22

## Context

Commit 8 completed deterministic simulation, append-only command-batch journaling,
historical replay, continuous target curves, official-distance authority and safe-wall coach
profile replacement. Session reports must derive from those authoritative facts without
creating a second live state machine, inventing observations, changing coach targets or
turning reports into domain events.

The first Commit 9 implementation exposed ten correctness gaps: replacement profiles were
not available to the normal CLI, report identity omitted non-event inputs, schema identity
could disagree with the contract, mismatched workout/profile/timeline inputs were accepted,
out-of-session observations were used, velocity-only trusted observations were ignored,
pending wall reconciliation was reported as completed, planned rest diluted quality ratios,
non-canonical report bytes were persisted, and absent directional extrema were represented by
synthetic zeroes. This correction makes those cases explicit invariants.

## Decision

A pure `analytics` package builds `SessionReport` 1.1 from:

1. canonical event envelopes,
2. a freshly verified `HistoricalSessionState`,
3. the workout and initial approved/compiled target timeline,
4. every replacement profile/timeline referenced by replayed coach-reset events,
5. optional explicitly trusted position or smoothed-velocity observations,
6. optional explicitly trusted HR/stroke observations,
7. a validated immutable analytics policy.

The append-only event journal remains authoritative. Reports are deterministic derived
artifacts and are never appended to the journal. The builder validates event ordering by
fresh replay and rejects a supplied replay state that disagrees with the stream.

## Input coherence

Before any metric is produced, the builder verifies:

- workout pool geometry equals replay geometry;
- workout, profile and compiled timeline distances agree;
- profile/timeline pool, stroke, start mode and workout goal agree where the workout schema
  carries those fields;
- timeline duration equals the profile target duration;
- timeline interval identity, source, type, start mode and version agree with its profile;
- the initial profile equals the profile selected by `SessionCreated`;
- each applied coach reset resolves to an explicitly supplied replacement profile/timeline;
- the final replay-selected profile is never silently replaced by the initial profile.

The report CLI accepts repeatable `--replacement-pace-profile` inputs and a profile-registry
directory. Missing reset runtime context is a typed input error, not `MISSING_TARGET` output.

## Identity and serialization

`reportSchemaVersion` is fixed by the `SessionReportV1_1` contract and builder to `1.1`; it
is not free-form caller input.

The builder records canonical SHA-256 digests for:

- canonical events,
- workout,
- initial profile,
- compiled timeline,
- replacement profile registry,
- observations,
- sensor observations,
- analytics policy.

Those digests are combined into `reportInputDigestSha256` and retained in provenance.
`reportId` is content-addressed: it is SHA-256 over canonical report content with only the
`reportId` field omitted. Therefore any metric, provenance or effective input change changes
the ID. Same inputs produce the same model, bytes, ID and SHA-256; different canonical report
content cannot share an ID.

`reportGeneratedAtMs` comes from the final authoritative event timestamp, never wall-clock
time. Canonical JSON is UTF-8, sorted-key, compact, finite-only and stable with explicit
`null` for absent optional values.

## Authority boundaries

- Official distance is only replayed wall-derived length count × pool geometry.
- Wearable or mid-pool observations never add official metres or official splits.
- An official wall split is not a profile leg or continuous phase; one split may overlap
  multiple target phases.
- Target values are sourced from locked constraints or the effective approved compiled
  timeline. Missing targets remain unavailable, never zero.
- Forecast fields are copied only when profile provenance already contains them. They never
  overwrite target fields and Commit 9 performs no forecasting inference.
- Dataset evidence IDs are copied only from approved profile provenance. Analytics reads no
  raw datasets and makes no license/eligibility decision.

## Timing and StopPause

Timing keeps separate axes:

`wall = elapsed + lifecyclePaused` and `elapsed = active + StopPause stopped`.

Planned rest, lifecycle pause, StopPause and coach pacing reset remain distinct. A resolved
StopPause may still have wall reconciliation pending. Reconciliation is counted only when an
actual later official `SplitRecorded` event occurs. Pending reconciliation has a separate
count/status, and `reconciledAtWallM` remains `null` until that official wall exists.

## Pacing analytics

Eligible official splits receive target/actual duration, cumulative time, speed and
AHEAD/ON_TARGET/BEHIND status. Exclusion policy and split quality are separate. Aggregates
exclude policy-ineligible splits but preserve them in the report. Central policies define
adherence tolerance, sustained-decline count/threshold, shape classification and unexpected
collapse margin. Collapse is advisory, not a diagnosis.

Fade uses:

`fadePct = (final eligible speed - initial eligible speed) / initial speed × 100`.

Negative values mean the swimmer slowed. Decline slope is dependency-free deterministic
least squares against normalized split position. Positive and negative extrema are optional:
if no split exists in a direction, the corresponding field is `null`, not fabricated `0`.

## Continuous curve analysis

Target distance comes only from the compiled timeline and active-time accounting. Actual
curve metrics accept either trusted smoothed position-time observations or trusted smoothed
velocity observations. Velocity-only sequences are deterministically integrated from the
session start or a trusted position anchor; they do not create official distance.

Every observation timestamp must lie within the authoritative session horizon:

`sessionStartMs <= timestampMs <= sessionEnd/reportHorizonMs`.

Planned-rest observations are excluded from both metrics and the relevant quality-ratio
denominator. The low-quality ratio is calculated only over relevant non-rest observations.
Raw stroke-cycle oscillation is not treated as the operational target envelope. Low-quality
or insufficient coverage produces an unavailable metric status; analytics never fabricates a
full curve. Signed distance deviation is:

`actualDistanceM - targetDistanceM` (positive = ahead, negative = behind).

## Sensor analysis

HR and stroke summaries are optional advisory outputs. Missing samples remain `None`.
Trend/correlation require minimum coverage and sample counts. Mixed stroke definitions are
rejected as low quality. No sensor metric changes the ghost, target or session state.

## Persistence and CLI

`SessionReportStore` is a persistence adapter for separate derived artifacts. Before writing,
it decodes the supplied bytes, validates `SessionReportV1_1`, re-encodes canonically and
requires exact byte equality. Pretty-printed or otherwise non-canonical JSON is rejected.
Writes use atomic temporary write, fsync and replace. Same ID/same bytes is idempotent; same
ID/different bytes is a conflict.

`swimtools.build_session_report` and `swimtools.verify_report` remain offline adapters over
replay/analytics and own no domain rules. The verifier validates canonical bytes, contract
schema, session identity, event horizon/digest and content-addressed report ID.

## Consequences

- `analytics` is a pure layer imported by simulator and swimtools, never by contracts or
  swimcore; it imports neither persistence nor simulator.
- Simulator runs generate and self-verify a report twice from the same journal.
- Coach-reset CLI reports require explicit replacement profile runtime context and retain
  correct pre/post-reset split provenance.
- Synthetic reports are explicitly marked and are not real performance evidence.
- SessionReport 1.0 and its schema remain unchanged; 1.1 is additive.

## Validation

Dedicated blocker-regression tests cover all ten corrected cases. Unit, property,
architecture, CLI, simulator acceptance and canonical golden-report tests cover determinism,
metric ranges, missing-data behavior, StopPause separation, safe-wall profile provenance,
trusted observation gates, canonical persistence and schema roundtrip.
