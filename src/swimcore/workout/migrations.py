"""Schema-version migration registry (pure functions).

Only a real ``1.0 → 1.0`` no-op is registered. No speculative future migrations are
invented. A migration is a pure function ``dict -> dict``.
"""

from __future__ import annotations

from collections.abc import Callable

MigrationFn = Callable[[dict[str, object]], dict[str, object]]


def _noop_1_0(document: dict[str, object]) -> dict[str, object]:
    return document


#: (from_version, to_version) -> migration function.
MIGRATIONS: dict[tuple[str, str], MigrationFn] = {
    ("1.0", "1.0"): _noop_1_0,
}

#: The single schema version this codebase currently targets.
CURRENT_SCHEMA_VERSION = "1.0"


def has_migration_path(from_version: str, to_version: str = CURRENT_SCHEMA_VERSION) -> bool:
    return (from_version, to_version) in MIGRATIONS


def migrate(
    document: dict[str, object],
    from_version: str,
    to_version: str = CURRENT_SCHEMA_VERSION,
) -> dict[str, object]:
    fn = MIGRATIONS.get((from_version, to_version))
    if fn is None:
        raise KeyError(f"no migration registered for {from_version} -> {to_version}")
    return fn(document)
