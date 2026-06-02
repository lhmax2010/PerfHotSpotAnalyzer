"""JSON Schema and semantic validation for the M0 data contracts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator


REPO_ROOT = Path(__file__).resolve().parents[1]

PERFORMANCE_FINDINGS = "performance-findings"
SUGGESTION_PATCH = "suggestion-patch"
CAPTURE_BUNDLE = "capture-bundle"

ANCHOR_METHOD_RELIABILITY = {
    "dwarf": 0,
    "addr2line": 1,
    "ctags": 2,
    "compile-db": 3,
    "grep": 4,
    "bench-name-map": 5,
    "caller-attribution": 6,
    "llm": 7,
}

KIND_TO_REPORT_TYPE = {
    "function-hotspot": "hotspot-profile",
    "binary-size-large": "binary-size",
    "binary-size-regression": "binary-size",
    "benchmark-regression": "benchmark",
    "benchmark-latency": "benchmark",
}

DEFAULT_SCHEMA_PATHS = {
    PERFORMANCE_FINDINGS: REPO_ROOT
    / "common"
    / "schemas"
    / "performance-findings.schema.json",
    SUGGESTION_PATCH: REPO_ROOT / "common" / "schemas" / "suggestion-patch.schema.json",
    CAPTURE_BUNDLE: REPO_ROOT / "common" / "schemas" / "capture-bundle.schema.json",
}

SKILL_SCHEMA_PATHS = {
    ("perf-hotspot-analyzer", PERFORMANCE_FINDINGS): DEFAULT_SCHEMA_PATHS[
        PERFORMANCE_FINDINGS
    ],
    ("perf-suggestion-patch", PERFORMANCE_FINDINGS): DEFAULT_SCHEMA_PATHS[
        PERFORMANCE_FINDINGS
    ],
    ("perf-suggestion-patch", SUGGESTION_PATCH): DEFAULT_SCHEMA_PATHS[SUGGESTION_PATCH],
    ("perf-hotspot-analyzer", CAPTURE_BUNDLE): DEFAULT_SCHEMA_PATHS[CAPTURE_BUNDLE],
}


@dataclass(frozen=True)
class ValidationIssue:
    """One structural or semantic validation failure."""

    rule: str
    path: str
    message: str

    def format(self) -> str:
        location = self.path or "$"
        return f"{self.rule} at {location}: {self.message}"


class SchemaValidationError(ValueError):
    """Raised when a document violates schema or semantic validation."""

    def __init__(self, issues: Sequence[ValidationIssue]) -> None:
        self.issues = list(issues)
        super().__init__("\n".join(issue.format() for issue in self.issues))


def load_json(path: str | Path) -> Any:
    json_path = Path(path)
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def detect_document_type(document: Mapping[str, Any]) -> str:
    if document.get("schema_version") == "capture-bundle/v1":
        return CAPTURE_BUNDLE
    if "patches" in document:
        return SUGGESTION_PATCH
    if "findings" in document:
        return PERFORMANCE_FINDINGS
    raise ValueError("cannot infer document type; expected 'findings' or 'patches'")


def resolve_schema_path(
    document_type: str,
    *,
    schema_path: str | Path | None = None,
    skill: str | None = None,
) -> Path:
    if schema_path is not None:
        return Path(schema_path)
    if skill is not None and (skill, document_type) in SKILL_SCHEMA_PATHS:
        return SKILL_SCHEMA_PATHS[(skill, document_type)]
    try:
        return DEFAULT_SCHEMA_PATHS[document_type]
    except KeyError as exc:
        raise ValueError(f"unknown document type: {document_type}") from exc


def validate_file(
    document_path: str | Path,
    *,
    document_type: str | None = None,
    schema_path: str | Path | None = None,
    skill: str | None = None,
) -> None:
    document = load_json(document_path)
    validate_document(
        document,
        document_type=document_type,
        schema_path=schema_path,
        skill=skill,
    )


def validate_document(
    document: Mapping[str, Any],
    *,
    document_type: str | None = None,
    schema_path: str | Path | None = None,
    skill: str | None = None,
) -> None:
    issues = collect_validation_issues(
        document,
        document_type=document_type,
        schema_path=schema_path,
        skill=skill,
    )
    if issues:
        raise SchemaValidationError(issues)


def collect_validation_issues(
    document: Mapping[str, Any],
    *,
    document_type: str | None = None,
    schema_path: str | Path | None = None,
    skill: str | None = None,
) -> list[ValidationIssue]:
    doc_type = document_type or detect_document_type(document)
    schema = load_json(resolve_schema_path(doc_type, schema_path=schema_path, skill=skill))
    validator = Draft202012Validator(schema)

    issues: list[ValidationIssue] = []
    for error in sorted(validator.iter_errors(document), key=lambda err: list(err.path)):
        issues.append(
            ValidationIssue(
                rule="json-schema",
                path=_json_path(error.absolute_path),
                message=error.message,
            )
        )

    issues.extend(_semantic_issues(document, doc_type))
    return issues


def _semantic_issues(document: Mapping[str, Any], document_type: str) -> list[ValidationIssue]:
    if document_type == PERFORMANCE_FINDINGS:
        return _performance_findings_semantic_issues(document)
    if document_type == SUGGESTION_PATCH:
        return _suggestion_patch_semantic_issues(document)
    if document_type == CAPTURE_BUNDLE:
        return []
    return [
        ValidationIssue(
            rule="document-type",
            path="$",
            message=f"unsupported document type: {document_type}",
        )
    ]


def _performance_findings_semantic_issues(
    document: Mapping[str, Any],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    source_reports = document.get("source_reports", [])
    findings = document.get("findings", [])
    source_by_id = {
        source.get("id"): source
        for source in source_reports
        if isinstance(source, Mapping) and source.get("id") is not None
    }

    expected_report_types = {
        KIND_TO_REPORT_TYPE.get(finding.get("kind"))
        for finding in findings
        if isinstance(finding, Mapping)
    }
    expected_report_types.discard(None)
    actual_report_types = document.get("report_types", [])
    if (
        not isinstance(actual_report_types, list)
        or set(actual_report_types) != expected_report_types
        or len(actual_report_types) != len(set(actual_report_types))
    ):
        issues.append(
            ValidationIssue(
                rule="report-types-consistency",
                path="$.report_types",
                message=(
                    "report_types must equal the de-duplicated set derived from "
                    f"findings[].kind: {sorted(expected_report_types)}"
                ),
            )
        )

    for index, finding in enumerate(findings):
        if not isinstance(finding, Mapping):
            continue
        source_id = _source_id(finding)
        if source_id not in source_by_id:
            issues.append(
                ValidationIssue(
                    rule="source-ref-validity",
                    path=f"$.findings[{index}].source_ref.source_id",
                    message=f"source_id {source_id!r} is not present in source_reports[].id",
                )
            )
            continue

        finding_confidence = finding.get("confidence")
        source_confidence = source_by_id[source_id].get("confidence")
        if (
            isinstance(finding_confidence, int | float)
            and isinstance(source_confidence, int | float)
            and finding_confidence > source_confidence
        ):
            issues.append(
                ValidationIssue(
                    rule="confidence-upper-bound",
                    path=f"$.findings[{index}].confidence",
                    message=(
                        "finding confidence must not exceed source_reports "
                        f"confidence {source_confidence}"
                    ),
                )
            )

        issues.extend(_finding_actionability_issues(finding, index))

    has_benchmark_regression = any(
        isinstance(finding, Mapping)
        and finding.get("kind") == "benchmark-regression"
        for finding in findings
    )
    baseline_report = (
        document.get("comparison", {}).get("baseline_report")
        if isinstance(document.get("comparison"), Mapping)
        else None
    )
    if has_benchmark_regression and not baseline_report:
        issues.append(
            ValidationIssue(
                rule="benchmark-regression-baseline",
                path="$.comparison.baseline_report",
                message="benchmark-regression findings require a non-empty baseline_report",
            )
        )

    return issues


def derive_effective_anchor(finding: Mapping[str, Any]) -> Mapping[str, Any] | None:
    attribution_anchor = finding.get("attribution_anchor")
    if isinstance(attribution_anchor, Mapping):
        return attribution_anchor

    code_anchors = finding.get("code_anchors", [])
    if not isinstance(code_anchors, list):
        return None
    anchors = [anchor for anchor in code_anchors if isinstance(anchor, Mapping)]
    if not anchors:
        return None

    return max(
        anchors,
        key=lambda anchor: (
            _anchor_confidence(anchor),
            -ANCHOR_METHOD_RELIABILITY.get(str(anchor.get("resolution_method")), 999),
        ),
    )


def _finding_actionability_issues(
    finding: Mapping[str, Any],
    index: int,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    kind = finding.get("kind")
    ownership = finding.get("ownership")
    actionability = finding.get("actionability")
    attribution_anchor = finding.get("attribution_anchor")
    has_attribution_anchor = isinstance(attribution_anchor, Mapping)

    if kind != "function-hotspot":
        return issues

    if (
        ownership is not None
        and ownership != "owned"
        and not has_attribution_anchor
        and actionability == "actionable"
    ):
        issues.append(
            ValidationIssue(
                rule="actionability-consistency",
                path=f"$.findings[{index}].actionability",
                message=(
                    "non-owned actionable findings require attribution_anchor; "
                    "otherwise actionability must be informational or not-actionable"
                ),
            )
        )

    if actionability == "actionable" and ownership != "owned":
        if not has_attribution_anchor:
            issues.append(
                ValidationIssue(
                    rule="attribution-completeness",
                    path=f"$.findings[{index}].attribution_anchor",
                    message="actionable non-owned findings require attribution_anchor",
                )
            )
        elif _anchor_confidence(attribution_anchor) < 0.7:
            issues.append(
                ValidationIssue(
                    rule="attribution-completeness",
                    path=f"$.findings[{index}].attribution_anchor.anchor_confidence",
                    message="attribution_anchor confidence must be at least 0.7",
                )
            )

    evidence = finding.get("evidence")
    hot_symbol = evidence.get("hot_symbol") if isinstance(evidence, Mapping) else None
    if not isinstance(hot_symbol, Mapping):
        issues.append(
            ValidationIssue(
                rule="function-hotspot-anchoring",
                path=f"$.findings[{index}].evidence.hot_symbol",
                message="function-hotspot findings require evidence.hot_symbol",
            )
        )

    if actionability == "actionable" and ownership == "owned":
        code_anchors = finding.get("code_anchors")
        if not isinstance(code_anchors, list) or not code_anchors:
            issues.append(
                ValidationIssue(
                    rule="function-hotspot-anchoring",
                    path=f"$.findings[{index}].code_anchors",
                    message="actionable owned function-hotspot findings require code_anchors",
                )
            )

    if actionability == "actionable" and ownership != "owned":
        if not has_attribution_anchor:
            issues.append(
                ValidationIssue(
                    rule="function-hotspot-anchoring",
                    path=f"$.findings[{index}].attribution_anchor",
                    message="actionable non-owned function-hotspot findings require attribution_anchor",
                )
            )
        elif _anchor_confidence(attribution_anchor) < 0.7:
            issues.append(
                ValidationIssue(
                    rule="function-hotspot-anchoring",
                    path=f"$.findings[{index}].attribution_anchor.anchor_confidence",
                    message="attribution_anchor confidence must be at least 0.7",
                )
            )

    return issues


def _suggestion_patch_semantic_issues(document: Mapping[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    patches = document.get("patches", [])
    for index, patch in enumerate(patches):
        if not isinstance(patch, Mapping):
            continue
        status = patch.get("status")
        has_diff = "diff" in patch
        has_anchor = "chosen_anchor" in patch
        has_recommendation = "recommendation" in patch

        if status == "advisory-only":
            if has_diff:
                issues.append(
                    ValidationIssue(
                        rule="per-status-consistency",
                        path=f"$.patches[{index}].diff",
                        message="advisory-only patches must not include diff",
                    )
                )
            if not has_recommendation:
                issues.append(
                    ValidationIssue(
                        rule="per-status-consistency",
                        path=f"$.patches[{index}].recommendation",
                        message="advisory-only patches require recommendation",
                    )
                )
        elif status in {"diff-ready", "needs-review"}:
            if not has_diff:
                issues.append(
                    ValidationIssue(
                        rule="per-status-consistency",
                        path=f"$.patches[{index}].diff",
                        message=f"{status} patches require diff",
                    )
                )
            if not has_anchor:
                issues.append(
                    ValidationIssue(
                        rule="per-status-consistency",
                        path=f"$.patches[{index}].chosen_anchor",
                        message=f"{status} patches require chosen_anchor",
                    )
                )

        if patch.get("measured_impact") is not None:
            issues.append(
                ValidationIssue(
                    rule="v1-invariants",
                    path=f"$.patches[{index}].measured_impact",
                    message="v1 requires measured_impact to be null",
                )
            )
        if patch.get("validation_status") != "not-run":
            issues.append(
                ValidationIssue(
                    rule="v1-invariants",
                    path=f"$.patches[{index}].validation_status",
                    message='v1 requires validation_status to be "not-run"',
                )
            )

    return issues


def _source_id(finding: Mapping[str, Any]) -> Any:
    source_ref = finding.get("source_ref")
    if isinstance(source_ref, Mapping):
        return source_ref.get("source_id")
    return None


def _anchor_confidence(anchor: Mapping[str, Any]) -> float:
    confidence = anchor.get("anchor_confidence", 0)
    if isinstance(confidence, int | float):
        return float(confidence)
    return 0.0


def _json_path(parts: Iterable[Any]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate performance skill JSON.")
    parser.add_argument("document", help="JSON document to validate")
    parser.add_argument(
        "--document-type",
        choices=[PERFORMANCE_FINDINGS, SUGGESTION_PATCH, CAPTURE_BUNDLE],
        help="Document type. Inferred when omitted.",
    )
    parser.add_argument("--schema", help="Override schema path")
    args = parser.parse_args(argv)

    try:
        validate_file(
            args.document,
            document_type=args.document_type,
            schema_path=args.schema,
        )
    except (OSError, json.JSONDecodeError, SchemaValidationError, ValueError) as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
