# Normalized research schema

Raw source validation and canonical normalization are separate operations.

1. `validate_dataset_bundle` checks exact ZIP/member hashes, row/column counts and **real raw
   headers**.
2. A normalized view applies the catalog's explicit `raw → canonical` mapping.
3. Missing source identity stays missing; no canonical ID is fabricated.

The common mapping is documented in `docs/data/raw-to-canonical-mapping.md` and encoded in
`DatasetFileManifest.normalizedColumnMapping`:

```text
source_participant_id -> subject_uid
session_or_trial_id   -> session_uid
record_granularity    -> record_type
```

Per-dataset expectations live in `data/schemas/` and use names such as
`requiredRawColumns`, `requiredRawColumnsByGranularity` and
`normalizedColumnMappingByFile` to prevent raw/canonical ambiguity.

The provider-independent record always preserves `data_domain`, source provenance,
missingness, license status and synthetic status. Target fields and forecast fields remain
separate. No normalized external record gains production eligibility merely by being
normalized.
