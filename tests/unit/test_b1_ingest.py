from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from common.schema_validate import SchemaValidationError


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "golden"
INGEST_PATH = ROOT / "skills" / "perf-suggestion-patch" / "scripts" / "ingest.py"


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("b1_ingest", INGEST_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_analyzer_json_preserves_source_report_identity() -> None:
    ingest = load_ingest_module()
    report = ingest.load_analyzer_json(
        FIXTURE_ROOT / "positive" / "01-hotspot-binary-size-mixed" / "performance-findings.json"
    )

    assert report.findings[0]["id"] == "F001"
    assert report.source_reports == [
        {
            "id": "S1",
            "source_format": "analyzer-json",
            "parser": "structured",
            "path": "perf.data",
            "confidence": 0.95,
        }
    ]
    assert report.source_formats == ["analyzer-json"]


def test_load_analyzer_json_keeps_nested_source_format_metadata() -> None:
    ingest = load_ingest_module()
    report = ingest.load_analyzer_json(
        FIXTURE_ROOT / "positive" / "15-attribution-third-party-owned" / "performance-findings.json"
    )

    source_report = report.source_reports[0]
    assert source_report["source_format"] == "perf-script"
    assert source_report["parser"] == "structured"
    assert source_report["confidence"] == 0.95


def test_load_analyzer_json_rejects_invalid_performance_findings() -> None:
    ingest = load_ingest_module()

    with pytest.raises(SchemaValidationError):
        ingest.load_analyzer_json(
            FIXTURE_ROOT
            / "negative"
            / "23-actionable-third-party-missing-attribution"
            / "performance-findings.json"
        )


def test_anchor_findings_scores_dwarf_and_handles_missing_anchor() -> None:
    ingest = load_ingest_module()
    report = ingest.load_analyzer_json(
        FIXTURE_ROOT / "positive" / "01-hotspot-binary-size-mixed" / "performance-findings.json"
    )

    anchored = ingest.anchor_findings(report.findings)

    assert anchored[0].effective_anchor["symbol"] == "decode_block"
    assert anchored[0].effective_anchor["anchor_confidence"] == 0.95
    assert anchored[0].effective_anchor["reported_anchor_confidence"] == 0.86
    assert anchored[1].effective_anchor is None
    assert anchored[1].anchor_confidence is None


def test_anchor_findings_prefers_attribution_anchor_and_scores_good_caller() -> None:
    ingest = load_ingest_module()
    report = ingest.load_analyzer_json(
        FIXTURE_ROOT
        / "positive"
        / "15-attribution-third-party-owned"
        / "performance-findings.json"
    )

    anchored = ingest.anchor_findings(report.findings)

    assert anchored[0].effective_anchor["symbol"] == "my_element_chain"
    assert anchored[0].effective_anchor["file"] == "src/element.c"
    assert anchored[0].effective_anchor["anchor_confidence"] == 0.80
    assert anchored[0].effective_anchor["reported_anchor_confidence"] == 0.82


def test_anchor_findings_returns_none_for_stack_without_owned_anchor() -> None:
    ingest = load_ingest_module()
    report = ingest.load_analyzer_json(
        FIXTURE_ROOT
        / "positive"
        / "16-attribution-no-owned-not-actionable"
        / "performance-findings.json"
    )

    anchored = ingest.anchor_findings(report.findings)

    assert anchored[0].effective_anchor is None
    assert anchored[0].anchor_confidence is None


def test_anchor_findings_uses_schema_validate_derive_effective_anchor(monkeypatch) -> None:
    ingest = load_ingest_module()
    calls = []

    def fake_derive(finding):
        calls.append(finding["id"])
        return {
            "symbol": "mapped_by_schema_validate",
            "file": "src/mapped.c",
            "line_start": 7,
            "line_end": 9,
            "anchor_confidence": 0.77,
            "resolution_method": "ctags",
        }

    monkeypatch.setattr(ingest.schema_validate, "derive_effective_anchor", fake_derive)

    anchored = ingest.anchor_findings([{"id": "F999"}])

    assert calls == ["F999"]
    assert anchored[0].effective_anchor["symbol"] == "mapped_by_schema_validate"
    assert anchored[0].effective_anchor["anchor_confidence"] == 0.75


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("dwarf", 0.95),
        ("addr2line", 0.85),
        ("ctags", 0.75),
        ("compile-db", 0.75),
        ("grep", 0.65),
        ("bench-name-map", 0.50),
        ("llm", 0.30),
    ],
)
def test_score_anchor_confidence_rubric_methods(method: str, expected: float) -> None:
    ingest = load_ingest_module()

    assert ingest.score_anchor_confidence({"resolution_method": method}) == expected


def test_score_anchor_confidence_caller_attribution_ambiguous_tier() -> None:
    ingest = load_ingest_module()

    score = ingest.score_anchor_confidence(
        {
            "resolution_method": "caller-attribution",
            "file": "src/hot.c",
            "line_start": 42,
            "anchor_confidence": 0.82,
            "evidence": "Manual review found multiple possible owned callers.",
        }
    )

    assert score == 0.65
