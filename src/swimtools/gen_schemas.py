"""Generate (or verify) the committed JSON Schemas from the pydantic contracts.

``python -m swimtools.gen_schemas``          → (re)writes src/contracts/schemas/*.json
``python -m swimtools.gen_schemas --check``  → fails if generated != committed

The schemas use only standard draft 2020-12 keywords. Output is deterministic
(``sort_keys=True``), so the committed files and the generated ones compare byte-for-byte.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from contracts.analytics import SessionReport
from contracts.continuous_pace import ApprovedContinuousPaceProfile
from contracts.event_log import EventBatchRecord
from contracts.events import EventEnvelope
from contracts.pace_profiles import ApprovedPaceProfile
from contracts.session_report import SessionReportV1_1
from contracts.workout import WorkoutTemplateV1_1, WorkoutTemplateVersion

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "contracts" / "schemas"

_MODELS: dict[str, type[BaseModel]] = {
    "workout-1.0.json": WorkoutTemplateVersion,
    "workout-1.1.json": WorkoutTemplateV1_1,
    "approved-pace-profile-1.0.json": ApprovedPaceProfile,
    "approved-pace-profile-1.1.json": ApprovedContinuousPaceProfile,
    "event-envelope-1.0.json": EventEnvelope,
    "event-batch-record-1.0.json": EventBatchRecord,
    "session-report-1.0.json": SessionReport,
    "session-report-1.1.json": SessionReportV1_1,
}

# Keys pydantic may emit that are OpenAPI-flavoured rather than pure JSON-Schema 2020-12.
_NON_STANDARD_KEYS = ("discriminator",)


def _strip_non_standard(node: Any) -> Any:
    """Remove non-standard keys so the schema stays pure draft 2020-12."""
    if isinstance(node, dict):
        return {k: _strip_non_standard(v) for k, v in node.items() if k not in _NON_STANDARD_KEYS}
    if isinstance(node, list):
        return [_strip_non_standard(v) for v in node]
    return node


def build_schema(model: type[BaseModel], schema_id: str) -> dict[str, Any]:
    raw: dict[str, Any] = model.model_json_schema()
    schema: dict[str, Any] = _strip_non_standard(raw)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://schemas.adaptiveswim.dev/{schema_id}"
    return schema


def _serialize(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def generate(check: bool) -> int:
    _SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    mismatches: list[str] = []
    for filename, model in _MODELS.items():
        target = _SCHEMA_DIR / filename
        rendered = _serialize(build_schema(model, filename))
        if check:
            if not target.exists():
                mismatches.append(f"{filename}: MISSING committed schema")
            elif target.read_text(encoding="utf-8") != rendered:
                mismatches.append(f"{filename}: committed schema differs from generated")
        else:
            target.write_text(rendered, encoding="utf-8")
    if check:
        if mismatches:
            print("schema-check FAILED:")
            for m in mismatches:
                print(f"  - {m}")
            return 1
        print("schema-check OK (generated == committed)")
        return 0
    print(f"wrote {len(_MODELS)} schema(s) to {_SCHEMA_DIR}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate/verify JSON Schemas.")
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    args = parser.parse_args(argv)
    return generate(check=args.check)


if __name__ == "__main__":
    sys.exit(main())
