"""Analyzer-json ingestion for the perf suggestion patch skill."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from common import schema_validate


@dataclass(frozen=True)
class IngestedReport:
    """Validated analyzer-json report with source metadata preserved."""

    path: Path
    document: dict[str, Any]
    source_reports: list[dict[str, Any]]
    findings: list[dict[str, Any]]

    @property
    def source_formats(self) -> list[str]:
        return [
            str(source_report["source_format"])
            for source_report in self.source_reports
            if "source_format" in source_report
        ]


@dataclass(frozen=True)
class AnchoredFinding:
    """Finding paired with the derived effective anchor and rubric score."""

    finding: dict[str, Any]
    effective_anchor: dict[str, Any] | None
    anchor_confidence: float | None


ANCHOR_RUBRIC: dict[str, float] = {
    "dwarf": 0.95,
    "addr2line": 0.85,
    "ctags": 0.75,
    "compile-db": 0.75,
    "grep": 0.65,
    "bench-name-map": 0.50,
    "llm": 0.30,
}


def load_analyzer_json(report_path: str | Path) -> IngestedReport:
    """Load and validate a canonical performance-findings report."""

    path = Path(report_path)
    document = schema_validate.load_json(path)
    schema_validate.validate_document(
        document,
        document_type=schema_validate.PERFORMANCE_FINDINGS,
        skill="perf-suggestion-patch",
    )

    return IngestedReport(
        path=path,
        document=document,
        source_reports=list(document.get("source_reports", [])),
        findings=list(document.get("findings", [])),
    )


def score_anchor_confidence(anchor: dict[str, Any] | None) -> float | None:
    """Score an anchor using the DESIGN §6.4 deterministic rubric."""

    if anchor is None:
        return None

    resolution_method = anchor.get("resolution_method")
    if resolution_method == "caller-attribution":
        if _is_confident_caller_attribution(anchor):
            return 0.80
        return 0.65

    return ANCHOR_RUBRIC.get(str(resolution_method), 0.30)


def anchor_findings(findings: list[dict[str, Any]]) -> list[AnchoredFinding]:
    """Derive and score effective anchors for every finding."""

    anchored: list[AnchoredFinding] = []
    for finding in findings:
        effective_anchor = schema_validate.derive_effective_anchor(finding)
        scored_anchor = _with_scored_confidence(effective_anchor)
        anchored.append(
            AnchoredFinding(
                finding=finding,
                effective_anchor=scored_anchor,
                anchor_confidence=(
                    scored_anchor.get("anchor_confidence") if scored_anchor is not None else None
                ),
            )
        )
    return anchored


def _with_scored_confidence(anchor: dict[str, Any] | None) -> dict[str, Any] | None:
    if anchor is None:
        return None

    scored_anchor = deepcopy(anchor)
    original_confidence = anchor.get("anchor_confidence")
    if original_confidence is not None:
        scored_anchor["reported_anchor_confidence"] = original_confidence
    scored_anchor["anchor_confidence"] = score_anchor_confidence(anchor)
    return scored_anchor


def _is_confident_caller_attribution(anchor: dict[str, Any]) -> bool:
    has_source_location = bool(anchor.get("file")) and isinstance(anchor.get("line_start"), int)
    reported_confidence = anchor.get("anchor_confidence")
    if not isinstance(reported_confidence, int | float):
        return False

    evidence = str(anchor.get("evidence", "")).lower()
    ambiguous_markers = ("ambiguous", "manual", "human", "llm", "multiple")
    return (
        has_source_location
        and float(reported_confidence) >= 0.70
        and not any(marker in evidence for marker in ambiguous_markers)
    )
