# DataSourceRegistry (ADR-032)

Her dis kaynak icin bir kayit. Belirsiz erisim/lisans -> `TBD_VERIFICATION_REQUIRED`.
ToS'u asan scraping planlanmaz.

Alanlar (18): sourceId, sourceName, ownerOrPublisher, sourceType, accessMethod, sourceUrlOrReference,
licenseStatus, commercialUseStatus, redistributionStatus, consentRequired, dataAvailabilityStatus,
availableFields, granularity, intendedRole (L1..L5), prohibitedUses, provenanceMethod, retrievalDate,
contentHashOrVersion, notes.

Bu contract Faz 1'de yalnizca `contracts/external_data.py` icinde plan-level olarak tanimlanir ve
`swimcore` tarafindan import EDILEMEZ (import-linter forbidden).
