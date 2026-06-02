from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from common.schema_validate import PERFORMANCE_FINDINGS, validate_document


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "golden"
INGEST_PATH = ROOT / "skills" / "perf-suggestion-patch" / "scripts" / "ingest.py"


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("b2_ingest_folded", INGEST_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_folded_stacks_fixture_normalizes_hotspots() -> None:
    ingest = load_ingest_module()
    report = ingest.load_folded_stacks(
        FIXTURE_ROOT / "positive" / "13-capture-bundle-10-piece" / "out.folded",
        repo_root="/repo/demo",
        target_name="demo-pipeline",
    )

    validate_document(report.document, document_type=PERFORMANCE_FINDINGS)
    assert report.source_reports[0]["source_format"] == "folded-stacks"
    assert report.findings[0]["source_ref"]["label"] == "g_signal_emit"
    assert report.findings[0]["evidence"]["samples"] == 42
    assert report.findings[0]["evidence"]["value"] == pytest.approx(76.363636)
    assert report.findings[0]["actionability"] == "informational"
    assert report.findings[0]["ownership"] == "unknown"


def test_folded_stacks_aggregates_duplicate_leaf_symbols(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    folded = tmp_path / "sample.folded"
    folded.write_text(
        "root;worker;hot_symbol 7\nroot;other;hot_symbol 3\nroot;cold 2\n",
        encoding="utf-8",
    )

    report = ingest.load_folded_stacks(folded)

    assert report.findings[0]["source_ref"]["label"] == "hot_symbol"
    assert report.findings[0]["evidence"]["samples"] == 10
    assert report.findings[1]["source_ref"]["label"] == "cold"


def test_folded_stacks_rejects_invalid_line(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    folded = tmp_path / "broken.folded"
    folded.write_text("root;worker;hot_symbol not-a-count\n", encoding="utf-8")

    with pytest.raises(ValueError):
        ingest.load_folded_stacks(folded)


def test_folded_stacks_e2e_writes_advisory_report(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    result = ingest.run_folded_stacks(
        FIXTURE_ROOT / "positive" / "13-capture-bundle-10-piece" / "out.folded",
        tmp_path,
        repo_root="/repo/demo",
    )

    assert result.run_report["input"]["source_formats"] == ["folded-stacks"]
    assert result.run_report["findings"]["by_kind"] == {"function-hotspot": 2}
    assert result.run_report["gate_decisions"][0]["reason"] == "actionability=informational"
    assert all("diff" not in patch for patch in result.suggestion_patch["patches"])
