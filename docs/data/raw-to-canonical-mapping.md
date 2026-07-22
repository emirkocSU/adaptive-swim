# Raw-to-canonical dataset mapping

The validator checks the **real raw CSV headers**. Canonical research names are created only
in a normalized view and are never required from a source file that does not contain them.
The machine-readable source is each file's `normalizedColumnMapping` in `data/catalog/*.json`.

## Standard mapping

| Raw source column | Canonical normalized-view column | Rule |
|---|---|---|
| `source_participant_id` | `subject_uid` | Preserve the source value; do not invent an athlete ID when blank. |
| `session_or_trial_id` | `session_uid` | Preserve the source trial/session identifier. |
| `record_granularity` | `record_type` | Preserve the raw granularity label (`ATHLETE_WEEK`, `SPRINT_REPEAT`, etc.). |

`athlete_pseudonym` remains available as provenance but is not silently substituted for a
missing `source_participant_id`. The quarantined stroke file has the three raw columns but
blank participant/session values; normalization therefore preserves blanks and never creates
identity.

## Bundle-specific mapping

- **Official race:** `subject_uid` is already a real raw header. `race_uid` is additionally
  exposed as canonical `session_uid`; raw `session_type` is exposed as `record_type`.
- **IMU:** `source_participant_id → subject_uid` and
  `session_or_trial_id → session_uid`. Sensor-sample granularity is catalog metadata; no
  nonexistent raw `record_type` is required.
- **Training/fatigue:** all three standard mappings apply. The validator counts
  `record_granularity`, not an invented `record_type` column.
- **External controlled studies, massage and quarantined stroke:** all three standard
  mappings apply per CSV member.

## API

`swimtools.data_catalog.normalize_raw_record(raw_record, member_manifest)` returns a new
mapping containing the untouched raw fields plus mapped canonical keys. It raises
`DatasetCatalogError` if a declared raw mapping source is absent.
