# External dataset metadata area

This directory contains only small catalog/schema metadata. Raw CSV/ZIP bundles are never
committed, packaged or placed under `src/`.

```text
data/external/raw/   local, gitignored operator mount
data/catalog/        exact bundle/member hashes, raw shapes, mappings and policies
data/schemas/        raw-header and normalized-view expectations
```

## Validator behavior

```bash
python -m swimtools.validate_dataset_bundle --bundle /path/to/bundle.zip
python -m swimtools.validate_dataset_bundle --all --data-root /path/to/four-zips
```

The validator streams ZIP members with the standard library, rejects unsafe/unexpected
members, and checks exact hashes/counts/raw headers. It does **not** expect invented raw
`subject_uid`, `session_uid` or `record_type` columns. These are produced by explicit
normalized mappings where applicable.

The external-studies ZIP is one seven-member bundle. Its stroke CSV is file-level
`SMOKE_TEST_ONLY`; a non-primary catalog alias exposes that policy without making CLI
validation treat the same ZIP as a second bundle.

License TBD/mixed/unverified remains production-blocking. None of the catalogued data is
measured instantaneous-velocity ground truth; IMU is not official distance.
