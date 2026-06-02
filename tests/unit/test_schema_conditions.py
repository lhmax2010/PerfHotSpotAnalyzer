from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from common.schema_validate import (
    PERFORMANCE_FINDINGS,
    SUGGESTION_PATCH,
    collect_validation_issues,
)


def base_performance(kind: str) -> dict:
    source_report = {
        "id": "S1",
        "path": "input.json",
        "source_format": "analyzer-json",
        "parser": "structured",
        "confidence": 0.9,
    }
    finding = {
        "id": "F001",
        "kind": kind,
        "title": "test finding",
        "source_ref": {"source_id": "S1", "locator": "$.x", "label": "x"},
        "evidence": {},
        "confidence": 0.8,
    }
    document = {
        "schema_version": "1.0",
        "report_types": [],
        "target": {
            "name": "demo",
            "kind": "binary",
            "platform": {"os": "linux", "arch": "x86_64"},
        },
        "source_reports": [source_report],
        "run_context": {"device": "host", "repeat_count": 1, "warmup_count": 0},
        "findings": [finding],
        "provenance": {
            "generated_by": "test",
            "version": "1.0.0",
            "timestamp": "2026-05-25T00:00:00Z",
        },
    }

    if kind == "function-hotspot":
        document["report_types"] = ["hotspot-profile"]
        document["profiling"] = {"tool": "perf", "callgraph_mode": "fp"}
        finding["ownership"] = "owned"
        finding["actionability"] = "actionable"
        finding["evidence"] = {
            "metric": "self_cpu_pct",
            "value": 38.2,
            "rank": 1,
            "hot_symbol": {
                "symbol": "hot",
                "dso": "demo",
                "ownership": "owned",
            },
        }
        finding["code_anchors"] = [
            {
                "symbol": "hot",
                "file": "src/hot.c",
                "line_start": 10,
                "line_end": 20,
                "anchor_confidence": 0.86,
                "resolution_method": "dwarf",
            }
        ]
    elif kind == "binary-size-large":
        document["report_types"] = ["binary-size"]
        finding["evidence"] = {
            "metric": "section_bytes",
            "value": 65536,
            "section": ".rodata",
            "file": "libdemo.so",
            "threshold": {
                "type": "absolute-bytes",
                "value": 65536,
                "unit": "bytes",
                "reason": "section exceeds 64KB",
            },
        }
    elif kind == "binary-size-regression":
        document["report_types"] = ["binary-size"]
        finding["evidence"] = {
            "section": ".text",
            "file": "libdemo.so",
            "baseline": {"value": 1000, "label": "main"},
            "delta": {"abs": 250, "pct": 25.0, "direction": "increase"},
        }
    elif kind == "benchmark-regression":
        document["report_types"] = ["benchmark"]
        document["comparison"] = {
            "current_report": "after.json",
            "baseline_report": "before.json",
            "compare_method": "name-match",
            "renamed_map": {},
        }
        finding["evidence"] = {
            "metric": "regression_pct",
            "baseline": {"value": 10.0, "label": "before"},
            "delta": {"abs": 2.0, "pct": 20.0, "direction": "increase"},
        }
    elif kind == "benchmark-latency":
        document["report_types"] = ["benchmark"]
        finding["evidence"] = {"metric": "latency_ms", "value": 12.3}
    else:
        raise AssertionError(f"unsupported kind {kind}")

    return document


def base_patch(status: str = "advisory-only") -> dict:
    patch = {
        "id": "P001",
        "finding_id": "F001",
        "source_ref": {"source_id": "S1", "locator": "$.x", "label": "x"},
        "patch_category": "local-micro-optimization",
        "files_touched": ["src/hot.c"],
        "files_touched_policy": {
            "allowed": True,
            "reason": "source file",
            "risk": "low",
        },
        "expected_impact": {"level": "medium", "estimate": "~5%", "confidence": 0.7},
        "measured_impact": None,
        "side_effects": {"runtime_memory": "unknown"},
        "risk": {"level": "low", "notes": "unit test fixture"},
        "rationale": "test rationale",
        "status": status,
        "validation_status": "not-run",
    }
    if status == "advisory-only":
        patch["recommendation"] = {
            "suggested_locations": ["src/hot.c:10"],
            "idea": "review hotspot",
            "risk": "low",
        }
    else:
        patch["diff"] = "--- a/src/hot.c\n+++ b/src/hot.c\n@@ -1 +1 @@\n-a\n+b\n"
        patch["chosen_anchor"] = {
            "symbol": "hot",
            "file": "src/hot.c",
            "line_start": 10,
            "line_end": 20,
            "anchor_confidence": 0.86,
            "resolution_method": "dwarf",
        }
    return {
        "schema_version": "1.0",
        "source_reports": [
            {
                "id": "S1",
                "path": "input.json",
                "source_format": "analyzer-json",
                "parser": "structured",
                "confidence": 0.9,
            }
        ],
        "patches": [patch],
        "apply_instructions": "Review manually; do not auto-apply.",
        "provenance": {
            "generated_by": "test",
            "version": "1.0.0",
            "timestamp": "2026-05-25T00:00:00Z",
        },
    }


def assert_valid(document: dict, document_type: str) -> None:
    assert collect_validation_issues(document, document_type=document_type) == []


def assert_invalid(document: dict, document_type: str) -> None:
    assert collect_validation_issues(document, document_type=document_type)


def test_per_kind_positive_examples_are_valid() -> None:
    for kind in [
        "function-hotspot",
        "binary-size-large",
        "binary-size-regression",
        "benchmark-regression",
        "benchmark-latency",
    ]:
        assert_valid(base_performance(kind), PERFORMANCE_FINDINGS)


def test_function_hotspot_requires_top_level_profiling() -> None:
    document = base_performance("function-hotspot")
    document.pop("profiling")
    assert_invalid(document, PERFORMANCE_FINDINGS)


def test_function_hotspot_requires_code_anchor() -> None:
    document = base_performance("function-hotspot")
    document["findings"][0]["code_anchors"] = []
    assert_invalid(document, PERFORMANCE_FINDINGS)


def test_binary_size_large_requires_threshold() -> None:
    document = base_performance("binary-size-large")
    document["findings"][0]["evidence"].pop("threshold")
    assert_invalid(document, PERFORMANCE_FINDINGS)


def test_binary_size_regression_requires_baseline_and_delta() -> None:
    document = base_performance("binary-size-regression")
    document["findings"][0]["evidence"].pop("baseline")
    assert_invalid(document, PERFORMANCE_FINDINGS)


def test_benchmark_regression_requires_comparison_baseline_report() -> None:
    document = base_performance("benchmark-regression")
    document["comparison"].pop("baseline_report")
    assert_invalid(document, PERFORMANCE_FINDINGS)


def test_benchmark_latency_requires_latency_metric() -> None:
    document = base_performance("benchmark-latency")
    document["findings"][0]["evidence"]["metric"] = "regression_pct"
    assert_invalid(document, PERFORMANCE_FINDINGS)


def test_per_status_positive_examples_are_valid() -> None:
    for status in ["advisory-only", "diff-ready", "needs-review"]:
        assert_valid(base_patch(status), SUGGESTION_PATCH)


def test_advisory_only_rejects_diff() -> None:
    document = base_patch("advisory-only")
    document["patches"][0]["diff"] = "--- a/x\n+++ b/x\n"
    assert_invalid(document, SUGGESTION_PATCH)


def test_diff_ready_requires_chosen_anchor() -> None:
    document = base_patch("diff-ready")
    document["patches"][0].pop("chosen_anchor")
    assert_invalid(document, SUGGESTION_PATCH)


def test_needs_review_requires_diff() -> None:
    document = base_patch("needs-review")
    document["patches"][0].pop("diff")
    assert_invalid(document, SUGGESTION_PATCH)


def test_skill_performance_schemas_are_identical() -> None:
    repo = Path(__file__).resolve().parents[2]
    canonical_schema = (
        repo / "common" / "schemas" / "performance-findings.schema.json"
    ).read_text(encoding="utf-8")
    analyzer_schema = (
        repo
        / "skills"
        / "perf-hotspot-analyzer"
        / "schemas"
        / "performance-findings.schema.json"
    ).read_text(encoding="utf-8")
    patch_schema = (
        repo
        / "skills"
        / "perf-suggestion-patch"
        / "schemas"
        / "performance-findings.schema.json"
    ).read_text(encoding="utf-8")
    assert canonical_schema == analyzer_schema == patch_schema


def test_suggestion_patch_schema_matches_canonical() -> None:
    repo = Path(__file__).resolve().parents[2]
    canonical_schema = (
        repo / "common" / "schemas" / "suggestion-patch.schema.json"
    ).read_text(encoding="utf-8")
    skill_schema = (
        repo
        / "skills"
        / "perf-suggestion-patch"
        / "schemas"
        / "suggestion-patch.schema.json"
    ).read_text(encoding="utf-8")
    assert canonical_schema == skill_schema


def test_mutating_fixture_copy_does_not_change_base() -> None:
    document = base_patch("diff-ready")
    mutated = deepcopy(document)
    mutated["patches"][0]["status"] = "advisory-only"
    assert document["patches"][0]["status"] == "diff-ready"
