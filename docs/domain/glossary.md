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
  the ten workout rules and returns `ValidationIssue`s. Takes an injected
  `WorkoutValidationContext`; queries no DB or device.
- **ValidationIssue** — `path` + `rule` + `message` + `severity` (`ERROR` / `WARNING`).
  Only an `ERROR` makes a workout invalid; a `WARNING` does not.
- **WorkoutValidationContext** — explicit external facts a rule may need (supported schema
  versions, max total distance, completed-session ids, coach-benchmark refs, supported
  feedback capabilities, strict-boundary mode). Absent context → context rules degrade to a
  documented WARNING.
