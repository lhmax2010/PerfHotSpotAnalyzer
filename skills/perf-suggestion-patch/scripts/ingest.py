"""Analyzer-json ingestion for the perf suggestion patch skill."""

from __future__ import annotations

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
