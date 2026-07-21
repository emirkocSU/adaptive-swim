"""Schema/version constants for the Adaptive Swim contracts."""

from __future__ import annotations

from typing import Final

#: Workout DSL schema version (semver-major; immutable once published).
WORKOUT_SCHEMA_VERSION: Final[str] = "1.0"

#: Event envelope schema version.
EVENT_ENVELOPE_SCHEMA_VERSION: Final[str] = "1.0"

#: Approved pace-profile schema versions.
APPROVED_PACE_PROFILE_SCHEMA_VERSION: Final[str] = "1.0"
APPROVED_CONTINUOUS_PACE_PROFILE_SCHEMA_VERSION: Final[str] = "1.1"

#: Session report schema version.
SESSION_REPORT_SCHEMA_VERSION: Final[str] = "1.0"

#: Event batch record (one persisted JSONL line per command) schema version.
EVENT_BATCH_RECORD_SCHEMA_VERSION: Final[str] = "1.0"

#: Versions the current codebase can read/produce.
SUPPORTED_WORKOUT_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset({"1.0"})

#: Event-envelope schema versions the replay/persistence layer can read.
SUPPORTED_EVENT_ENVELOPE_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset({"1.0"})

#: Event-batch-record versions the persistence codec can read.
SUPPORTED_EVENT_BATCH_RECORD_VERSIONS: Final[frozenset[str]] = frozenset({"1.0"})
