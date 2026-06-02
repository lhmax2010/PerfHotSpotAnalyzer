from __future__ import annotations

from copy import deepcopy

from common.schema_validate import (
    PERFORMANCE_FINDINGS,
    SUGGESTION_PATCH,
    collect_validation_issues,
    derive_effective_anchor,
)
from tests.unit.test_schema_conditions import base_patch, base_performance


def rules(document: dict, document_type: str) -> set[str]:
    return {
        issue.rule
        for issue in collect_validation_issues(document, document_type=document_type)
    }


def assert_rule(document: dict, document_type: str, rule: str) -> None:
    assert rule in rules(document, document_type)


def assert_no_rule(document: dict, document_type: str, rule: str) -> None:
    assert rule not in rules(document, document_type)


def test_rule_1_confidence_upper_bound_positive_and_negative() -> None:
    valid = base_performance("function-hotspot")
    assert_no_rule(valid, PERFORMANCE_FINDINGS, "confidence-upper-bound")

    invalid = deepcopy(valid)
    invalid["findings"][0]["confidence"] = 0.95
    assert_rule(invalid, PERFORMANCE_FINDINGS, "confidence-upper-bound")


def test_rule_2_report_types_consistency_positive_and_negative() -> None:
    valid = base_performance("binary-size-large")
    assert_no_rule(valid, PERFORMANCE_FINDINGS, "report-types-consistency")

    invalid = deepcopy(valid)
    invalid["report_types"] = ["hotspot-profile"]
    assert_rule(invalid, PERFORMANCE_FINDINGS, "report-types-consistency")


def test_rule_3_per_status_consistency_positive_and_negative() -> None:
    valid = base_patch("diff-ready")
    assert_no_rule(valid, SUGGESTION_PATCH, "per-status-consistency")

    invalid = deepcopy(valid)
    invalid["patches"][0].pop("diff")
    assert_rule(invalid, SUGGESTION_PATCH, "per-status-consistency")


def test_rule_4_v1_invariants_positive_and_negative() -> None:
    valid = base_patch("advisory-only")
    assert_no_rule(valid, SUGGESTION_PATCH, "v1-invariants")

    measured = deepcopy(valid)
    measured["patches"][0]["measured_impact"] = {"speedup": 1.2}
    assert_rule(measured, SUGGESTION_PATCH, "v1-invariants")

    validation = deepcopy(valid)
    validation["patches"][0]["validation_status"] = "test-pass"
    assert_rule(validation, SUGGESTION_PATCH, "v1-invariants")


def test_rule_5_source_ref_validity_positive_and_negative() -> None:
    valid = base_performance("benchmark-latency")
    assert_no_rule(valid, PERFORMANCE_FINDINGS, "source-ref-validity")

    invalid = deepcopy(valid)
    invalid["findings"][0]["source_ref"]["source_id"] = "missing"
    assert_rule(invalid, PERFORMANCE_FINDINGS, "source-ref-validity")


def test_rule_6_benchmark_regression_baseline_positive_and_negative() -> None:
    valid = base_performance("benchmark-regression")
    assert_no_rule(valid, PERFORMANCE_FINDINGS, "benchmark-regression-baseline")

    invalid = deepcopy(valid)
    invalid.pop("comparison")
    assert_rule(invalid, PERFORMANCE_FINDINGS, "benchmark-regression-baseline")


def test_rule_7_actionability_consistency_positive_and_negative() -> None:
    valid = base_performance("function-hotspot")
    valid["findings"][0]["ownership"] = "third-party"
    valid["findings"][0]["actionability"] = "not-actionable"
    valid["findings"][0].pop("code_anchors")
    valid["findings"][0]["evidence"]["hot_symbol"]["ownership"] = "third-party"
    assert_no_rule(valid, PERFORMANCE_FINDINGS, "actionability-consistency")

    invalid = deepcopy(valid)
    invalid["findings"][0]["actionability"] = "actionable"
    assert_rule(invalid, PERFORMANCE_FINDINGS, "actionability-consistency")


def test_rule_8_attribution_completeness_positive_and_negative() -> None:
    valid = base_performance("function-hotspot")
    finding = valid["findings"][0]
    finding["ownership"] = "third-party"
    finding["actionability"] = "actionable"
    finding["evidence"]["hot_symbol"]["ownership"] = "third-party"
    finding["attribution_anchor"] = {
        "symbol": "owned_call_site",
        "dso": "libowned.so",
        "file": "src/owned.c",
        "line_start": 10,
        "line_end": 20,
        "language": "c",
        "anchor_confidence": 0.82,
        "resolution_method": "caller-attribution",
        "evidence": "owned caller in the callgraph",
    }
    assert_no_rule(valid, PERFORMANCE_FINDINGS, "attribution-completeness")

    invalid = deepcopy(valid)
    invalid["findings"][0]["attribution_anchor"]["anchor_confidence"] = 0.62
    assert_rule(invalid, PERFORMANCE_FINDINGS, "attribution-completeness")


def test_rule_9_function_hotspot_anchoring_positive_and_negative() -> None:
    valid = base_performance("function-hotspot")
    assert_no_rule(valid, PERFORMANCE_FINDINGS, "function-hotspot-anchoring")

    invalid = deepcopy(valid)
    invalid["findings"][0]["evidence"].pop("hot_symbol")
    assert_rule(invalid, PERFORMANCE_FINDINGS, "function-hotspot-anchoring")


def test_rule_10_effective_anchor_prefers_attribution_anchor() -> None:
    document = base_performance("function-hotspot")
    finding = document["findings"][0]
    finding["ownership"] = "third-party"
    finding["actionability"] = "actionable"
    finding["evidence"]["hot_symbol"]["ownership"] = "third-party"
    finding["code_anchors"] = [
        {
            "symbol": "third_party_hot",
            "dso": "libthirdparty.so",
            "file": "thirdparty/hot.c",
            "line_start": 1,
            "line_end": 2,
            "language": "c",
            "anchor_confidence": 0.95,
            "resolution_method": "dwarf",
        }
    ]
    finding["attribution_anchor"] = {
        "symbol": "owned_call_site",
        "dso": "libowned.so",
        "file": "src/owned.c",
        "line_start": 10,
        "line_end": 20,
        "language": "c",
        "anchor_confidence": 0.82,
        "resolution_method": "caller-attribution",
    }

    assert derive_effective_anchor(finding)["symbol"] == "owned_call_site"


def test_rule_10_effective_anchor_uses_best_code_anchor_when_no_attribution() -> None:
    document = base_performance("function-hotspot")
    finding = document["findings"][0]
    finding["code_anchors"] = [
        {
            "symbol": "grep_candidate",
            "file": "src/hot.c",
            "line_start": 10,
            "line_end": 20,
            "anchor_confidence": 0.82,
            "resolution_method": "grep",
        },
        {
            "symbol": "dwarf_candidate",
            "file": "src/hot.c",
            "line_start": 10,
            "line_end": 20,
            "anchor_confidence": 0.82,
            "resolution_method": "dwarf",
        },
    ]

    assert derive_effective_anchor(finding)["symbol"] == "dwarf_candidate"
