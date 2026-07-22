"""Deterministic event, input, and content-addressed report identity helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from analytics.types import ReportBuildContext
from contracts.events import EventEnvelope
from contracts.session_report import SessionReportV1_1


def _normalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=False)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _normalize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        normalized_items = [(_normalize(key), _normalize(item)) for key, item in value.items()]
        normalized_items.sort(key=lambda pair: _canonical_json_bytes(pair[0]))
        return [{"key": key, "value": item} for key, item in normalized_items]
    if isinstance(value, list | tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    raise TypeError(f"unsupported deterministic digest value: {type(value).__name__}")


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(_normalize(value))).hexdigest()


def report_policy_digest_sha256(context: ReportBuildContext) -> str:
    """Hash only the effective analytics/report policy of a build context.

    ``simulationRunId`` is an output identity and ``profileRegistry`` is already covered by
    the explicit profile digests.  Excluding both prevents an identity cycle while ensuring
    every threshold/version flag that can change analytics output participates in the run
    identity.
    """

    payload = {
        "analyticsVersion": context.analyticsVersion,
        "reportBuilderVersion": context.reportBuilderVersion,
        "reportSchemaVersion": context.reportSchemaVersion,
        "reportVersion": context.reportVersion,
        "adherenceToleranceSec": context.adherenceToleranceSec,
        "onTargetTolerancePct": context.onTargetTolerancePct,
        "curveAdherenceToleranceM": context.curveAdherenceToleranceM,
        "minimumTrustedCurveObservations": context.minimumTrustedCurveObservations,
        "minimumCurveCoverageRatio": context.minimumCurveCoverageRatio,
        "maximumLowQualityObservationRatio": context.maximumLowQualityObservationRatio,
        "minimumConsecutiveDecliningSplits": context.minimumConsecutiveDecliningSplits,
        "minimumDeclinePct": context.minimumDeclinePct,
        "unexpectedCollapseMarginPct": context.unexpectedCollapseMarginPct,
        "minimumPacingShapeSplits": context.minimumPacingShapeSplits,
        "minimumSensorSamplesForTrend": context.minimumSensorSamplesForTrend,
        "simulatorSynthetic": context.simulatorSynthetic,
    }
    return canonical_digest_sha256(payload)


def canonical_event_bytes(events: Sequence[EventEnvelope]) -> bytes:
    payload = [event.model_dump(mode="json", exclude_none=False) for event in events]
    return _canonical_json_bytes(payload)


def event_digest_sha256(events: Sequence[EventEnvelope]) -> str:
    return hashlib.sha256(canonical_event_bytes(events)).hexdigest()


def canonical_report_identity_bytes(report: SessionReportV1_1) -> bytes:
    """Return canonical report bytes with ``reportId`` excluded.

    Report identity is content-addressed. Consequently every provenance/input digest and
    every computed output field participates in the ID, while the ID itself does not.
    """

    payload = report.model_dump(mode="json", exclude_none=False)
    payload.pop("reportId", None)
    return _canonical_json_bytes(payload)


def deterministic_report_id(report: SessionReportV1_1) -> str:
    """Hash the complete deterministic report content except for the ID itself."""

    return hashlib.sha256(canonical_report_identity_bytes(report)).hexdigest()


__all__ = [
    "canonical_digest_sha256",
    "canonical_event_bytes",
    "canonical_report_identity_bytes",
    "deterministic_report_id",
    "event_digest_sha256",
    "report_policy_digest_sha256",
]
