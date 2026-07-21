# ADR-037 — Append-Only Event Journal and Deterministic Historical Replay

- **Status:** ACTIVE (Faz 1, Commit 7)
- **Date:** 2026-07-19
- **Related:** ADR-003 (SQLite WAL — Faz 2), ADR-006 (in-process bus + JSONL), ADR-012
  (golden replay), ADR-031 (StopPause), ADR-033 (deterministic identity/time), ADR-036
  (official-distance authority)

## Context / Problem

`SessionAggregate` produces typed domain events in memory (Commit 6). They must be stored
durably and the session's past state must be reproducible deterministically — without a
database, without a server, fully offline. A single command can emit several events
(`CreateSession` → `WorkoutValidated` + `SessionCreated`); persisting them as separate
lines allows a crash to make only *half a command* durable.

## Decision

### Command-batch-per-line JSONL

All events of one `handle(command)` call form one `EventBatchRecord` and are persisted as
**one canonical JSONL line**. A half-written final line therefore removes the whole
command batch — a partial command never replays. Per-event lines are forbidden.

### Canonical codec

One authoritative byte encoding (`persistence.codec`): UTF-8 (no BOM), `sort_keys`,
compact separators, `allow_nan=False`, exactly one `\n`. The same record always encodes to
byte-for-byte identical output; NaN/Infinity are rejected on encode **and** decode. Raw
JSON/Unicode/Pydantic errors never escape the public API (`__cause__` preserved).

### Append-only + fsync-per-command-batch

The whole line is prepared as a single bytes buffer, written through a partial-write- and
EINTR-safe loop, then `os.fsync`'ed. Success is reported **only after** write + fsync both
completed. When the journal file is first created, the parent directory entry is synced as
well. No background writer thread, no timer-based batching.

### Fsync and kill -9 semantics (honesty clause)

Surviving `kill -9` is **not** the same as surviving a power cut. `fsync` is a durability
*request* to the filesystem and storage stack; for hardware failure no absolute guarantee
is claimed. What Commit 7 guarantees is ordering + atomic command batches + explicit
recovery semantics.

### Exact-duplicate idempotency

Resending the exact same batch (canonically identical bytes for the same
`clientCommandId`) never writes a second line: the journal re-fsyncs the existing line and
returns `ALREADY_PRESENT`. Same seq / same command id / partial seq overlap with
*different* content is a typed conflict. After an fsync failure
(`EventLogDurabilityUncertainError`) the fully-written line is recognised on retry — the
retry re-fsyncs, never duplicates.

### Partial final-tail recovery

- Final record valid, newline missing → accepted; repair appends only `\n`
  (`MissingFinalNewlineRepaired`; *not* data loss).
- Final line torn (undecodable) → only the incomplete tail is truncated
  (`ftruncate` + fsync, `LogTailTruncated` with exact byte counts). Bytes before the last
  complete newline are never touched.
- `read_all(repair_tail=False)` never modifies the file (torn tail → `TailRepairError`);
  `recover_and_read()` repairs explicitly and idempotently.

### Middle corruption is never skipped

An invalid line before the tail, an invalid **newline-terminated** final line, or a blank
line is `CorruptEventLogError`. The reader never skips to later valid lines.

### Event-derived pure replay

`swimcore.replay.replay_session(events)` folds typed events into a
`HistoricalSessionState`. Replay executes no commands, never rewinds the runtime
`ActiveClock`/`GhostClock`, uses no real time/randomness/uuid/filesystem, and reuses the
authoritative lifecycle transition table (`swimcore.session.transitions`) — a second
transition implementation is forbidden. Official distance comes only from pool geometry
((lengthIndex + 1) × poolLengthM); a wearable estimate never appears (ADR-036). Replay is
a **historical read model**: live command-ready aggregate recovery is a later architecture
stage.

### Lifecycle pause vs StopPause (separate duration axes)

`horizon = terminal event time (else last event time)`;
`wall = horizon − startedAtMs`; `lifecyclePaused = pause intervals (+ open to horizon)`;
`stopped = resolved StopPause intervals (+ open stop startedAtMs → horizon)`;
`elapsed = wall − lifecyclePaused`; `active = elapsed − stopped`.
Invariants `elapsed = active + stopped` and `wall = elapsed + lifecyclePaused` are
enforced; negative or contradictory durations are `ReplayDurationError`. The retroactive
stop start is the payload `startedAtMs`, never the confirmation event's timestamp. An open
lifecycle pause and an open StopPause at the same time is stream corruption.

### Explicit SessionRecovered marker

Reading a journal never auto-produces `SessionRecovered` and nothing auto-appends it. An
explicit helper (`persistence.recovery.build_session_recovered_event`) builds the typed
event with an injected Clock + EventIdGenerator; persisting it is a caller decision. On
replay it changes no lifecycle state and only increments `recoveryCount`.

### SQLite deferred to Faz 2

The JSONL journal is the authoritative history. SQLite WAL is a *projection* added in
Faz 2 (ADR-003); log-first ordering stays. No DB/ORM/WAL projection/event-store server in
Commit 7.

## Commands
None added — persistence consumes command *results* (event batches).

## Events
`SessionRecovered` gains its typed payload (`SessionRecoveredPayload`). `EventBatchRecord`
is a persistence contract (recordVersion 1.0, generated schema
`event-batch-record-1.0.json`).

## State changes
New pure read model `HistoricalSessionState` (lifecycle, splits + verifications, StopPause
intervals, coach-reset pending marker, applied pace, control decision, profile/pool/start
metadata, five duration fields, `recoveryCount`).

## Analytics consequences
Commit 9 analytics can be computed from replayed state instead of live memory; active vs
stopped vs lifecycle-paused time is already separated per ADR-031.

## ML consequences
None in Faz 1. The journal later feeds `ADAPTIVE_SWIM_SESSION` external-data records with
full provenance (ADR-032); replay does not label anything.

## Reversibility
The journal format is versioned (`recordVersion`); an incompatible future format is a new
version read by a new codec. Dropping the layer costs one package (`persistence`) plus
`swimcore.replay`; `swimcore` has no dependency on either.

## Validation tests
`tests/replay/` (contract, codec, journal, idempotency, tail recovery, failure injection,
lifecycle/split/StopPause/pacing/validation replay, golden journals),
`tests/property/test_replay_invariants.py`,
`tests/architecture/test_replay_boundaries.py`. Golden journals are byte-deterministic
(sha256-equal across directories) per ADR-012/ADR-033.
