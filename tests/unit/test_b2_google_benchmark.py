from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from common.schema_validate import PERFORMANCE_FINDINGS, validate_document


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "golden"
INGEST_PATH = ROOT / "skills" / "perf-suggestion-patch" / "scripts" / "ingest.py"


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("b2_ingest_google", INGEST_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_google_benchmark_before_after_normalizes_regression() -> None:
    ingest = load_ingest_module()
    report = ingest.load_google_benchmark(
        FIXTURE_ROOT / "positive" / "02-google-benchmark-before-after" / "after.json",
        baseline_report=(
            FIXTURE_ROOT / "positive" / "02-google-benchmark-before-after" / "before.json"
        ),
        repo_root="/repo/demo",
        target_name="decode-bench",
    )

    validate_document(report.document, document_type=PERFORMANCE_FINDINGS)
    finding = report.findings[0]
    assert finding["kind"] == "benchmark-regression"
    assert finding["evidence"]["value"] == 25.0
    assert finding["evidence"]["baseline"]["value"] == 10.0
    assert finding["evidence"]["delta"] == {
        "abs": 2.5,
        "pct": 25.0,
        "direction": "increase",
    }
    assert report.document["comparison"]["baseline_report"].endswith("before.json")
    assert [source["source_format"] for source in report.source_reports] == [
        "google-benchmark",
        "google-benchmark",
    ]


def test_google_benchmark_single_report_normalizes_latency() -> None:
    ingest = load_ingest_module()
    report = ingest.load_google_benchmark(
        FIXTURE_ROOT / "positive" / "03-google-benchmark-single-latency" / "current.json",
        repo_root="/repo/demo",
        target_name="lookup-bench",
    )

    validate_document(report.document, document_type=PERFORMANCE_FINDINGS)
    finding = report.findings[0]
    assert finding["kind"] == "benchmark-latency"
    assert finding["evidence"] == {
        "metric": "latency_ms",
        "value": 3.7,
        "unit": "ms",
    }
    assert "comparison" not in report.document


def test_google_benchmark_renamed_map_pairs_current_to_baseline(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    current = tmp_path / "after.json"
    baseline = tmp_path / "before.json"
    current.write_text(
        json.dumps({"benchmarks": [{"name": "BM_New", "real_time": 1500, "time_unit": "us"}]}),
        encoding="utf-8",
    )
    baseline.write_text(
        json.dumps({"benchmarks": [{"name": "BM_Old", "real_time": 1, "time_unit": "ms"}]}),
        encoding="utf-8",
    )

    report = ingest.load_google_benchmark(
        current,
        baseline_report=baseline,
        renamed_map={"BM_New": "BM_Old"},
    )

    finding = report.findings[0]
    assert finding["source_ref"]["label"] == "BM_New"
    assert finding["evidence"]["baseline_name"] == "BM_Old"
    assert finding["evidence"]["value"] == 50.0
    assert report.document["comparison"]["compare_method"] == "manual-map"


def test_google_benchmark_e2e_latency_gate_reason(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    result = ingest.run_google_benchmark(
        FIXTURE_ROOT / "positive" / "03-google-benchmark-single-latency" / "current.json",
        tmp_path,
        repo_root="/repo/demo",
    )

    decision = result.run_report["gate_decisions"][0]
    assert result.suggestion_patch["patches"][0]["status"] == "advisory-only"
    assert "diff" not in result.suggestion_patch["patches"][0]
    assert "benchmark-latency-without-perf-budget" in decision["reason"]
