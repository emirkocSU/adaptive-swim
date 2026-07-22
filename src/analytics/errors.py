"""Typed failures raised by deterministic report construction."""


class AnalyticsError(Exception):
    """Base class for report/analytics failures."""


class ReportInputError(AnalyticsError):
    """Required report input is missing or contradictory."""


class ReplayStateMismatchError(AnalyticsError):
    """Supplied HistoricalSessionState does not match replay of the event stream."""


class ObservationValidationError(AnalyticsError):
    """Observation sequence violates monotonicity or finite-value requirements."""


class ReportIdentityError(AnalyticsError):
    """A deterministic report identity check failed."""


class ReportStoreConflictError(AnalyticsError):
    """A different report attempted to reuse an existing deterministic report id."""
