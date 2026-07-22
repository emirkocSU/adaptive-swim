from __future__ import annotations

from tests.unit._analytics_helpers import report


def test_report_provenance_is_grounded_in_inputs() -> None:
    provenance = report().provenance
    assert provenance.eventFirstSeq == 1
    assert provenance.eventLastSeq == provenance.eventCount
    assert len(provenance.eventDigestSha256) == 64
    assert provenance.datasetEvidenceAssetIds == ()
