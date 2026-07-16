# Data Source Registry

Every external data source is registered as a `DataSourceRegistryEntry` before use. No
access/download/commercial/redistribution right is assumed. Ambiguous license or access
is recorded as `TBD_VERIFICATION_REQUIRED`. Scraping beyond a source's ToS/data license
is not planned.

Fields (plan-level, see `src/contracts/external_data.py`): sourceId, sourceName,
ownerOrPublisher, sourceType, accessMethod, sourceUrlOrReference, licenseStatus,
commercialUseStatus, redistributionStatus, consentRequired, dataAvailabilityStatus,
availableFields, granularity, intendedRole (L1..L5), prohibitedUses, provenanceMethod,
retrievalDate, contentHashOrVersion, notes.
