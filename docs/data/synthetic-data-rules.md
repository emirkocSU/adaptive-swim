# Synthetic Data Rules

- Every synthetic record carries `synthetic=true` plus scenario/seed provenance.
- Synthetic data is **not** sporting-performance evidence and is never used in a
  production-accuracy claim.
- Synthetic and real records are never merged by hiding the source; `data_domain` and
  provenance are always preserved.
- Missingness is preserved; no fake filling.
