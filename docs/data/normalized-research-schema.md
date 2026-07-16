# Normalized Research Schema (provider-independent, plan-level)

`NormalizedSwimmingRecord` is a provider-independent research schema draft. It always
carries a `data_domain`; records from different domains cannot be merged without it.
Missingness is preserved (Optional fields; no fake filling). Synthetic records carry
`synthetic=true` and a provenance reference. No production-eligibility flag exists on any
external record.
