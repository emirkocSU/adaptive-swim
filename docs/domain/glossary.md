# Domain Glossary

- **Ghost** — the personal pacer the swimmer follows; driven by a pure `pace_function(t)`.
- **Pacing-related delay / normal pace loss** — the swimmer tiring or slowing. Ghost stays
  `ACTIVE`; the workout clock keeps running; the gap is preserved and counts toward
  performance.
- **Coach pacing reset** — a separate command that starts a new pacing reference at the
  next valid wall. Previous performance stays in the report. Not a StopPause.
- **StopPause** — the general runtime behaviour when a stop is verified (manual incident,
  coach stop, or long-stop threshold). The logical workout clock freezes from the stop
  start; the ghost aligns to the swimmer (mid-pool allowed) and waits; accounting is
  reconciled at the next wall.
- **Incident** — only a *trigger/reason* (`StopPauseTrigger.MANUAL_INCIDENT`), never a
  behaviour name.
- **Length** — one pool length (e.g. 25 m or 50 m).
- **Segment** — a `fromM..toM` span of a repeat block with a target pace and a mode.
- **Gap** — signed difference between ghost and swimmer position/time.
- **Wall reconciliation** — finalizing length/set/rest accounting at the next valid wall.
- **Active / stopped / elapsed duration** — active swim time, stopped time, and real
  total; displayed as `active +stopped` (e.g. `20.00 +15.00` → 35.00 total).
- **Structural validation** — the generated JSON Schema layer: shape, types, ranges,
  `additionalProperties: false`. No domain/semantic rule lives here.
- **Semantic validator** — the Commit 3 pure domain layer (`swimcore/workout/`) that runs
  the twelve workout rules and returns `ValidationIssue`s. Takes an injected
  `WorkoutValidationContext`; queries no DB or device.
- **ValidationIssue** — `path` + `rule` + `message` + `severity` (`ERROR` / `WARNING`).
  Only an `ERROR` makes a workout invalid; a `WARNING` does not.
- **WorkoutValidationContext** — explicit external facts a rule may need (supported schema
  versions, max total distance, completed-session ids, coach-benchmark refs, supported
  feedback capabilities, strict-boundary mode). Absent context → context rules degrade to a
  documented WARNING.
- **Pace timeline** — the Commit 4 compilation of a workout into ordered pace intervals in
  global distance, carrying **active swimming time only** (rest/StopPause excluded).
- **Active-time pace math** — pure functions mapping distance ↔ active time along the
  timeline. `target_active_time_at_distance` and `ghost_distance_at_active_time` are exact
  inverses (linear pace ⇒ quadratic time integral).
- **Linear pace curve** — `p(x) = p0 + (p1−p0)·x/L` per segment; even/negative-split are
  constant, controlled_start runs start→target, progressive runs target→end.
- **Wall boundary** — a pool-length multiple; helpers (`is/previous/next_wall_boundary`)
  are pure and never move the ghost or mutate state.
- **SimClock** — deterministic, manually-advanced millisecond clock (no system time); the
  only time source injected into the simulator/tests. Bit-identical across identical runs.
- **ActiveClock** — separates wall elapsed from active swimming time
  (`active = wall − confirmed stopped`); applies StopPause freezes **retroactively** from the
  real stop start. A timing primitive, not a session state machine.
- **GhostClock** — drives the Commit-4 pace timeline by active time; ACTIVE / STOP_PAUSED.
  Aligns to an externally supplied tracked point only during a confirmed StopPause.
- **GhostAnchor** — immutable continuity anchor; `displayDistanceM = anchorDisplay +
  (timelineDistance(activeNow) − anchorTimeline)`, preventing a jump back to the plan.
- **timelineDistanceM vs displayDistanceM** — the unchanging mathematical plan position vs
  the shown position after a temporary alignment offset. Never conflate them.
- **Wall reconciliation** — converting a temporary mid-pool alignment into a safe forward
  wall anchor at the next valid wall; it does not touch length/set/split state (Commit 6).
- **Monotonic runtime clock** — ActiveClock only moves forward: a snapshot or query earlier
  than its last transition is rejected (`InvalidClockTimeError`). It is not an event store;
  historical replay is rebuilt from events in Commit 7.
- **Resume rule** — a StopPause resume may not precede its confirmation time
  (`resumedAtMs >= confirmedAtMs`).
- **Expected reconciliation wall** — the single wall (next valid wall after the tracked
  alignment, or the tracked wall itself if already on one) at which a pending StopPause
  alignment may be reconciled, exactly once. Computed with the authoritative wall helper.
- **InvalidPoolLengthError** — raised for a non-finite or non-positive pool length.
- **Forward-only watermark** — ActiveClock records the latest observed time on every query
  and transition; nothing may be observed earlier. A later snapshot cannot rewind active
  time, and a StopPause confirmation cannot precede the last observed time.
- **Finite-result guarantee** — every public pace-math function rejects not only NaN/inf
  inputs but also results that overflow to non-finite for huge finite inputs.
- **Wall-boundary total** — a GhostClock's timeline total distance must itself be a wall
  boundary for the pool; `next_wall_boundary` never returns a non-wall final distance.
- **ActiveClock forward-only rule** — ActiveClock is forward-only in observed wall time.
  Active elapsed may be retroactively corrected only when a StopPause is confirmed from an
  earlier stop-start timestamp (a single controlled decrease); it never becomes negative,
  stopped never becomes negative, and `wall = active + stopped` always holds.
- **StopPause non-overlap** — a new StopPause may not start before the previous completed
  StopPause's resume time (`stopStartedAtMs >= lastCompletedStopResumedAtMs`).
- **Session aggregate** — the Commit 6 pure orchestration object combining contracts,
  validator, timeline, clocks, ghost, and SafetyController; `handle(command)` returns
  in-memory events. No persistence/replay (Commit 7).
- **Session state** — CREATED/ARMED/RUNNING/PAUSED/COMPLETED/ABORTED. StopPause is not a
  lifecycle state; the session stays RUNNING while the ghost is STOP_PAUSED.
- **Idempotency (clientCommandId)** — a repeated command with identical content returns the
  same stored events without re-mutating; different content is a conflict.
- **SafetyController** — pure mandatory gate for pace changes; smaller sec/100m is faster;
  applied pace never breaches fastest/slowest/max-change; off/suggest_only/low-confidence/
  low-quality/not-at-wall abstain to the coach plan; NaN/inf/heart-rate-only are rejected;
  every decision carries reason codes. ML only suggests and never controls the ghost directly.
- **Wall reconciliation orchestration** — a wall `RecordSplit` matching the expected wall
  reconciles a pending StopPause alignment exactly once; mid-pool has no official accounting.
