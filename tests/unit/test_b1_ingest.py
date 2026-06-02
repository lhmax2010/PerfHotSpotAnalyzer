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
