"""Analyzer-json ingestion for the perf suggestion patch skill."""

from __future__ import annotations

import json
import time
import hashlib
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common import schema_validate
from common.tracing import TraceLogger, start_trace


ANCHOR_GATE_THRESHOLD = 0.70


@dataclass(frozen=True)
class IngestedReport:
    """Validated performance-findings report with source metadata preserved."""

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


@dataclass(frozen=True)
class GateDecision:
    """B1 gate result for one finding."""

    finding_id: str
    status: str
    reason: str
    actionability: str
    effective_anchor: dict[str, Any] | None
    anchor_confidence: float | None

    def to_record(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "decision": self.status,
            "reason": self.reason,
            "actionability": self.actionability,
            "effective_anchor": self.effective_anchor,
            "anchor_confidence": self.anchor_confidence,
        }


@dataclass(frozen=True)
class AnalysisResult:
    """Paths and documents produced by an ingest run."""

    patches_path: Path
    run_report_path: Path
    suggestion_patch: dict[str, Any]
    run_report: dict[str, Any]


@dataclass(frozen=True)
class GenericLLMProtocolPaths:
    """Prompt and output paths for the generic-llm normalization handoff."""

    report_id: str
    prompt_path: Path
    output_path: Path


class GenericLLMOutputPending(RuntimeError):
    """Raised when the host Agent has not written the normalized JSON yet."""

    def __init__(self, paths: GenericLLMProtocolPaths) -> None:
        self.paths = paths
        super().__init__(
            "generic-llm normalization is pending; prompt written to "
            f"{paths.prompt_path}, expected normalized JSON at {paths.output_path}"
        )


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


def load_google_benchmark(
    report_path: str | Path,
    *,
    baseline_report: str | Path | None = None,
    repo_root: str | Path | None = None,
    renamed_map: dict[str, str] | None = None,
    target_name: str | None = None,
) -> IngestedReport:
    """Normalize Google Benchmark JSON into a performance-findings report."""

    path = Path(report_path)
    current_document = schema_validate.load_json(path)
    baseline_path = Path(baseline_report) if baseline_report is not None else None
    baseline_document = (
        schema_validate.load_json(baseline_path) if baseline_path is not None else None
    )
    document = normalize_google_benchmark(
        current_document,
        current_path=path,
        baseline_document=baseline_document,
        baseline_path=baseline_path,
        repo_root=repo_root,
        renamed_map=renamed_map or {},
        target_name=target_name,
    )
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


def load_folded_stacks(
    report_path: str | Path,
    *,
    repo_root: str | Path | None = None,
    target_name: str | None = None,
    top_n: int = 20,
) -> IngestedReport:
    """Normalize folded stack samples into function-hotspot findings."""

    path = Path(report_path)
    text = path.read_text(encoding="utf-8")
    document = normalize_folded_stacks(
        text,
        report_path=path,
        repo_root=repo_root,
        target_name=target_name,
        top_n=top_n,
    )
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


def load_generic_llm(
    report_path: str | Path,
    *,
    output_dir: str | Path,
    repo_root: str | Path | None = None,
    target_name: str | None = None,
) -> IngestedReport:
    """Read a host-normalized generic report after writing the prompt handoff."""

    raw_path = Path(report_path)
    paths = prepare_generic_llm_protocol(
        raw_path,
        output_dir=output_dir,
        repo_root=repo_root,
        target_name=target_name,
    )
    if not paths.output_path.exists():
        raise GenericLLMOutputPending(paths)

    document = schema_validate.load_json(paths.output_path)
    document = normalize_generic_llm_document(
        document,
        raw_path=raw_path,
        repo_root=repo_root,
        target_name=target_name,
    )
    schema_validate.validate_document(
        document,
        document_type=schema_validate.PERFORMANCE_FINDINGS,
        skill="perf-suggestion-patch",
    )
    return IngestedReport(
        path=raw_path,
        document=document,
        source_reports=list(document.get("source_reports", [])),
        findings=list(document.get("findings", [])),
    )


def prepare_generic_llm_protocol(
    report_path: str | Path,
    *,
    output_dir: str | Path,
    repo_root: str | Path | None = None,
    target_name: str | None = None,
) -> GenericLLMProtocolPaths:
    """Write the prompt that asks the host Agent to normalize free-form input."""

    raw_path = Path(report_path)
    output_path = Path(output_dir)
    report_id = _generic_report_id(raw_path)
    prompts_dir = output_path / "prompts"
    normalized_dir = output_path / "outputs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    paths = GenericLLMProtocolPaths(
        report_id=report_id,
        prompt_path=prompts_dir / f"{report_id}-normalize.prompt.md",
        output_path=normalized_dir / f"{report_id}-normalized.json",
    )
    raw_text = raw_path.read_text(encoding="utf-8")
    paths.prompt_path.write_text(
        _generic_llm_prompt(
            raw_text=raw_text,
            raw_path=raw_path,
            normalized_output=paths.output_path,
            repo_root=repo_root,
            target_name=target_name,
        ),
        encoding="utf-8",
    )
    return paths


def normalize_generic_llm_document(
    document: dict[str, Any],
    *,
    raw_path: Path,
    repo_root: str | Path | None = None,
    target_name: str | None = None,
) -> dict[str, Any]:
    """Enforce generic-llm source metadata and low parser confidence."""

    normalized = deepcopy(document)
    normalized["schema_version"] = "1.0"
    target = normalized.setdefault("target", {})
    target.setdefault("name", target_name or raw_path.stem)
    target.setdefault("kind", "service")
    target["repo_root"] = str(repo_root) if repo_root is not None else target.get("repo_root", "")
    target.setdefault("platform", {"os": "linux", "arch": "x86_64"})
    normalized.setdefault(
        "run_context",
        {
            "device": "host",
            "cpu_governor": "unknown",
            "core_count": 1,
            "repeat_count": 1,
            "warmup_count": 0,
        },
    )
    normalized["source_reports"] = [
        {
            "id": "S1",
            "path": str(raw_path),
            "source_format": "generic-llm",
            "parser": "generic-llm",
            "confidence": 0.30,
        }
    ]
    findings = normalized.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            source_ref = finding.setdefault("source_ref", {"source_id": "S1"})
            source_ref["source_id"] = "S1"
            confidence = finding.get("confidence", 0.30)
            if isinstance(confidence, int | float):
                finding["confidence"] = min(float(confidence), 0.30)
            else:
                finding["confidence"] = 0.30
            finding["source_format"] = "generic-llm"
            _set_generic_default_actionability(finding)
    normalized["report_types"] = _derive_report_types(normalized.get("findings", []))
    provenance = normalized.setdefault("provenance", {})
    provenance.setdefault("generated_by", "host-agent-generic-llm")
    provenance.setdefault("version", "1.0.0-b2")
    provenance.setdefault("timestamp", datetime.now(UTC).isoformat())
    return normalized


def normalize_folded_stacks(
    text: str,
    *,
    report_path: Path,
    repo_root: str | Path | None = None,
    target_name: str | None = None,
    top_n: int = 20,
) -> dict[str, Any]:
    """Build a canonical performance-findings document from folded stacks."""

    symbol_counts = _aggregate_folded_leaf_samples(text)
    total_samples = sum(symbol_counts.values())
    if total_samples <= 0:
        raise ValueError("folded stacks must contain at least one positive sample")

    findings = []
    for index, (symbol, samples) in enumerate(
        sorted(symbol_counts.items(), key=lambda item: (-item[1], item[0]))[:top_n],
        start=1,
    ):
        pct = (samples / total_samples) * 100.0
        findings.append(
            {
                "id": f"F{index:03d}",
                "kind": "function-hotspot",
                "title": f"{symbol} is hot in folded stacks",
                "source_ref": {
                    "source_id": "S1",
                    "locator": f"symbol:{symbol}",
                    "label": symbol,
                },
                "ownership": "unknown",
                "actionability": "informational",
                "evidence": {
                    "metric": "self_cpu_pct",
                    "value": round(pct, 6),
                    "unit": "percent",
                    "samples": samples,
                    "rank": index,
                    "hot_symbol": {
                        "symbol": symbol,
                        "dso": "unknown",
                        "ownership": "unknown",
                    },
                },
                "diagnosis": (
                    "Folded stack aggregation found a hot symbol, but no deterministic "
                    "source anchor is available yet."
                ),
                "confidence": 0.75,
            }
        )

    return {
        "schema_version": "1.0",
        "report_types": ["hotspot-profile"],
        "target": {
            "name": target_name or report_path.stem,
            "kind": "process",
            "repo_root": str(repo_root) if repo_root is not None else "",
            "platform": {"os": "linux", "arch": "x86_64"},
        },
        "source_reports": [
            {
                "id": "S1",
                "path": str(report_path),
                "source_format": "folded-stacks",
                "parser": "structured",
                "confidence": 0.85,
            }
        ],
        "run_context": {
            "device": "host",
            "cpu_governor": "unknown",
            "core_count": 1,
            "repeat_count": 1,
            "warmup_count": 0,
        },
        "profiling": {
            "tool": "perf",
            "events": ["cycles"],
            "callgraph_mode": "none",
            "artifacts": {"folded": str(report_path)},
        },
        "findings": findings,
        "provenance": {
            "generated_by": "perf-suggestion-patch.ingest",
            "version": "1.0.0-b2",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }


def normalize_google_benchmark(
    current_document: dict[str, Any],
    *,
    current_path: Path,
    baseline_document: dict[str, Any] | None = None,
    baseline_path: Path | None = None,
    repo_root: str | Path | None = None,
    renamed_map: dict[str, str] | None = None,
    target_name: str | None = None,
) -> dict[str, Any]:
    """Build a canonical performance-findings document from GB JSON."""

    renamed = renamed_map or {}
    current_benchmarks = _google_benchmark_entries(current_document)
    baseline_benchmarks = (
        _google_benchmark_entries(baseline_document) if baseline_document else []
    )
    baseline_by_name = {str(item.get("name")): item for item in baseline_benchmarks}
    source_reports = [
        {
            "id": "S1",
            "path": str(current_path),
            "source_format": "google-benchmark",
            "parser": "structured",
            "confidence": 0.98,
        }
    ]
    if baseline_path is not None:
        source_reports.append(
            {
                "id": "S2",
                "path": str(baseline_path),
                "source_format": "google-benchmark",
                "parser": "structured",
                "confidence": 0.98,
            }
        )

    findings = []
    for index, benchmark in enumerate(current_benchmarks, start=1):
        name = str(benchmark["name"])
        current_ms = _benchmark_latency_ms(benchmark)
        if baseline_document is not None:
            baseline_name = _baseline_name_for(name, renamed)
            baseline = baseline_by_name.get(baseline_name)
            if baseline is None:
                continue
            baseline_ms = _benchmark_latency_ms(baseline)
            findings.append(
                _build_benchmark_regression_finding(
                    index=index,
                    name=name,
                    baseline_name=baseline_name,
                    current_ms=current_ms,
                    baseline_ms=baseline_ms,
                    current_path=current_path,
                    baseline_path=baseline_path,
                )
            )
        else:
            findings.append(
                _build_benchmark_latency_finding(
                    index=index,
                    name=name,
                    current_ms=current_ms,
                )
            )

    document = {
        "schema_version": "1.0",
        "report_types": ["benchmark"],
        "target": {
            "name": target_name or current_path.stem,
            "kind": "benchmark-suite",
            "repo_root": str(repo_root) if repo_root is not None else "",
            "platform": {"os": "linux", "arch": "x86_64"},
        },
        "source_reports": source_reports,
        "run_context": {
            "device": "host",
            "cpu_governor": "unknown",
            "core_count": 1,
            "repeat_count": 1,
            "warmup_count": 0,
        },
        "findings": findings,
        "provenance": {
            "generated_by": "perf-suggestion-patch.ingest",
            "version": "1.0.0-b2",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }
    if baseline_document is not None and baseline_path is not None:
        document["comparison"] = {
            "current_report": str(current_path),
            "baseline_report": str(baseline_path),
            "compare_method": "manual-map" if renamed else "name-match",
            "renamed_map": renamed,
        }
    return document


def score_anchor_confidence(anchor: dict[str, Any] | None) -> float | None:
    """Score an anchor using the DESIGN section 6.4 deterministic rubric."""

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


def gate_findings(anchored_findings: list[AnchoredFinding]) -> list[GateDecision]:
    """Apply B1 actionability and effective-anchor gates."""

    return [_gate_finding(anchored) for anchored in anchored_findings]


def build_suggestion_patch(
    report: IngestedReport,
    anchored_findings: list[AnchoredFinding],
    gate_decisions: list[GateDecision],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build an advisory-only suggestion-patch document for B1."""

    decision_by_finding = {
        decision.finding_id: decision for decision in gate_decisions
    }
    patches = []
    for index, anchored in enumerate(anchored_findings, start=1):
        finding = anchored.finding
        decision = decision_by_finding[str(finding["id"])]
        patches.append(_build_advisory_patch(index, anchored, decision))

    suggestion_patch = {
        "schema_version": "1.0",
        "source_reports": report.source_reports,
        "patches": patches,
        "apply_instructions": (
            "B1 emits advisory-only recommendations. Do not apply generated "
            "changes automatically; review each recommendation manually."
        ),
        "provenance": {
            "generated_by": "perf-suggestion-patch.ingest",
            "version": "1.0.0-b1",
            "timestamp": generated_at or datetime.now(UTC).isoformat(),
            "input_report": str(report.path),
        },
    }
    schema_validate.validate_document(
        suggestion_patch,
        document_type=schema_validate.SUGGESTION_PATCH,
        skill="perf-suggestion-patch",
    )
    return suggestion_patch


def run_analyzer_json(
    report_path: str | Path,
    output_dir: str | Path,
    *,
    verbose: bool = False,
    tracer: TraceLogger | None = None,
) -> AnalysisResult:
    """Run the B1 analyzer-json pipeline and write validated outputs."""

    report = load_analyzer_json(report_path)
    return run_ingested_report(
        report,
        output_dir,
        verbose=verbose,
        tracer=tracer,
    )


def run_google_benchmark(
    report_path: str | Path,
    output_dir: str | Path,
    *,
    baseline_report: str | Path | None = None,
    repo_root: str | Path | None = None,
    renamed_map: dict[str, str] | None = None,
    target_name: str | None = None,
    verbose: bool = False,
    tracer: TraceLogger | None = None,
) -> AnalysisResult:
    """Run the B2 Google Benchmark adapter and advisory output path."""

    report = load_google_benchmark(
        report_path,
        baseline_report=baseline_report,
        repo_root=repo_root,
        renamed_map=renamed_map,
        target_name=target_name,
    )
    return run_ingested_report(
        report,
        output_dir,
        verbose=verbose,
        tracer=tracer,
    )


def run_folded_stacks(
    report_path: str | Path,
    output_dir: str | Path,
    *,
    repo_root: str | Path | None = None,
    target_name: str | None = None,
    verbose: bool = False,
    tracer: TraceLogger | None = None,
) -> AnalysisResult:
    """Run the B2 folded-stacks adapter and advisory output path."""

    report = load_folded_stacks(
        report_path,
        repo_root=repo_root,
        target_name=target_name,
    )
    return run_ingested_report(
        report,
        output_dir,
        verbose=verbose,
        tracer=tracer,
    )


def run_generic_llm(
    report_path: str | Path,
    output_dir: str | Path,
    *,
    repo_root: str | Path | None = None,
    target_name: str | None = None,
    verbose: bool = False,
    tracer: TraceLogger | None = None,
) -> AnalysisResult:
    """Run the generic-llm prompt handoff adapter and advisory output path."""

    report = load_generic_llm(
        report_path,
        output_dir=output_dir,
        repo_root=repo_root,
        target_name=target_name,
    )
    return run_ingested_report(
        report,
        output_dir,
        verbose=verbose,
        tracer=tracer,
    )


def run_ingest(
    report_path: str | Path,
    output_dir: str | Path,
    *,
    input_format: str = "auto",
    baseline_report: str | Path | None = None,
    repo_root: str | Path | None = None,
    renamed_map: dict[str, str] | None = None,
    target_name: str | None = None,
    verbose: bool = False,
) -> AnalysisResult:
    """Dispatch an input report to a B2 adapter."""

    detected_format = (
        detect_input_format(report_path) if input_format == "auto" else input_format
    )
    if detected_format == "analyzer-json":
        return run_analyzer_json(report_path, output_dir, verbose=verbose)
    if detected_format == "google-benchmark":
        return run_google_benchmark(
            report_path,
            output_dir,
            baseline_report=baseline_report,
            repo_root=repo_root,
            renamed_map=renamed_map,
            target_name=target_name,
            verbose=verbose,
        )
    if detected_format == "folded-stacks":
        return run_folded_stacks(
            report_path,
            output_dir,
            repo_root=repo_root,
            target_name=target_name,
            verbose=verbose,
        )
    if detected_format == "generic-llm":
        return run_generic_llm(
            report_path,
            output_dir,
            repo_root=repo_root,
            target_name=target_name,
            verbose=verbose,
        )
    raise ValueError(f"unsupported input format for B2: {detected_format}")


def detect_input_format(report_path: str | Path) -> str:
    """Detect the adapter for a report path."""

    path = Path(report_path)
    if path.suffix.lower() == ".json":
        document = schema_validate.load_json(path)
        if isinstance(document, dict) and "benchmarks" in document:
            return "google-benchmark"
        if isinstance(document, dict) and "findings" in document:
            return "analyzer-json"
    if path.suffix.lower() in {".folded", ".collapsed"}:
        return "folded-stacks"
    return "generic-llm"


def run_ingested_report(
    report: IngestedReport,
    output_dir: str | Path,
    *,
    verbose: bool = False,
    tracer: TraceLogger | None = None,
) -> AnalysisResult:
    """Run anchor, gate, and advisory report generation for a normalized report."""

    report = enrich_report_with_repo_anchors(report)
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    owns_tracer = tracer is None
    active_tracer = tracer or start_trace(
        skill="perf-suggestion-patch",
        output_dir=output_path,
        verbose=verbose,
    )
    step_ms: dict[str, int] = {}

    try:
        step_started = time.monotonic()
        active_tracer.info(
            "ingest",
            "success",
            document=str(report.path),
            findings=len(report.findings),
            source_formats=report.source_formats,
        )
        step_ms["ingest"] = _elapsed_ms(step_started)

        step_started = time.monotonic()
        active_tracer.info("anchor", "start", findings=len(report.findings))
        anchored_findings = anchor_findings(report.findings)
        step_ms["anchor"] = _elapsed_ms(step_started)
        active_tracer.info(
            "anchor",
            "success",
            resolved=sum(1 for anchored in anchored_findings if anchored.effective_anchor),
        )

        step_started = time.monotonic()
        active_tracer.info("gate", "start", findings=len(report.findings))
        gate_decisions = gate_findings(anchored_findings)
        step_ms["gate"] = _elapsed_ms(step_started)
        active_tracer.info(
            "gate",
            "success",
            advisory_only=sum(
                1 for decision in gate_decisions if decision.status == "advisory-only"
            ),
        )

        step_started = time.monotonic()
        suggestion_patch = build_suggestion_patch(
            report,
            anchored_findings,
            gate_decisions,
            generated_at=started_at,
        )
        patches_path = output_path / "patches.json"
        patches_path.write_text(
            json.dumps(suggestion_patch, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        step_ms["report"] = _elapsed_ms(step_started)
        active_tracer.info("report", "success", patches=str(patches_path))

        total_ms = _elapsed_ms(started)
        run_report = build_run_report(
            report=report,
            anchored_findings=anchored_findings,
            gate_decisions=gate_decisions,
            trace_id=active_tracer.trace_id,
            started_at=started_at,
            total_ms=total_ms,
            step_ms=step_ms,
            exit_status="success",
            errors=[],
        )
        run_report_path = output_path / "run-report.json"
        run_report_path.write_text(
            json.dumps(run_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return AnalysisResult(
            patches_path=patches_path,
            run_report_path=run_report_path,
            suggestion_patch=suggestion_patch,
            run_report=run_report,
        )
    finally:
        if owns_tracer:
            active_tracer.close()


def enrich_report_with_repo_anchors(report: IngestedReport) -> IngestedReport:
    """Add deterministic repo-root anchors to normalized external findings."""

    repo_root = report.document.get("target", {}).get("repo_root")
    if not repo_root:
        return report
    repo_path = Path(str(repo_root)).expanduser()
    if not repo_path.exists() or not repo_path.is_dir():
        return report

    document = deepcopy(report.document)
    changed = False
    for finding in document.get("findings", []):
        if not isinstance(finding, dict):
            continue
        anchors = _repo_anchors_for_finding(finding, repo_path)
        if not anchors:
            continue
        existing = [
            anchor for anchor in finding.get("code_anchors", []) if isinstance(anchor, dict)
        ]
        for anchor in anchors:
            if not _has_equivalent_anchor(existing, anchor):
                existing.append(anchor)
                changed = True
        finding["code_anchors"] = existing
        if finding.get("kind") == "function-hotspot":
            finding["ownership"] = "owned"
            finding["actionability"] = "actionable"

    if not changed:
        return report

    schema_validate.validate_document(
        document,
        document_type=schema_validate.PERFORMANCE_FINDINGS,
        skill="perf-suggestion-patch",
    )
    return IngestedReport(
        path=report.path,
        document=document,
        source_reports=list(document.get("source_reports", [])),
        findings=list(document.get("findings", [])),
    )


def build_run_report(
    *,
    report: IngestedReport,
    anchored_findings: list[AnchoredFinding],
    gate_decisions: list[GateDecision],
    trace_id: str,
    started_at: str,
    total_ms: int,
    step_ms: dict[str, int],
    exit_status: str,
    errors: list[str],
) -> dict[str, Any]:
    """Build the B1 run-report document."""

    return {
        "schema_version": "run-report/v1",
        "trace_id": trace_id,
        "skill": "perf-suggestion-patch",
        "started_at": started_at,
        "total_ms": total_ms,
        "by_step": step_ms,
        "input": {
            "path": str(report.path),
            "document_type": schema_validate.PERFORMANCE_FINDINGS,
            "source_formats": report.source_formats,
            "source_reports": report.source_reports,
        },
        "findings": {
            "total": len(report.findings),
            "by_kind": _count_by_key(report.findings, "kind"),
        },
        "anchors": {
            "resolved": sum(
                1 for anchored in anchored_findings if anchored.effective_anchor
            ),
            "confidence_distribution": _anchor_confidence_distribution(
                anchored_findings
            ),
        },
        "gate_decisions": [decision.to_record() for decision in gate_decisions],
        "patches": {
            "diff-ready": 0,
            "needs-review": 0,
            "advisory-only": len(gate_decisions),
        },
        "degradations": [
            decision.to_record()
            for decision in gate_decisions
            if decision.reason != "b1-advisory-only"
        ],
        "exit_status": exit_status,
        "errors": errors,
    }


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


def _gate_finding(anchored: AnchoredFinding) -> GateDecision:
    finding = anchored.finding
    finding_id = str(finding["id"])
    actionability = str(finding.get("actionability", "unknown"))

    if actionability != "actionable":
        reason = f"actionability={actionability}"
    else:
        reasons = []
        if anchored.effective_anchor is None:
            reasons.append("effective_anchor=null")
        elif (
            anchored.anchor_confidence is None
            or anchored.anchor_confidence < ANCHOR_GATE_THRESHOLD
        ):
            reasons.append(
                f"effective_anchor_confidence={anchored.anchor_confidence} "
                f"< {ANCHOR_GATE_THRESHOLD:.2f}"
            )
        if finding.get("kind") == "benchmark-latency" and not finding.get("perf_budget"):
            reasons.append("benchmark-latency-without-perf-budget")
        if (
            finding.get("source_format") == "generic-llm"
            and not _generic_llm_anchor_can_continue(anchored.effective_anchor)
        ):
            reasons.append("generic-llm-default-advisory")
        reason = "; ".join(reasons) if reasons else "b1-advisory-only"

    return GateDecision(
        finding_id=finding_id,
        status="advisory-only",
        reason=reason,
        actionability=actionability,
        effective_anchor=anchored.effective_anchor,
        anchor_confidence=anchored.anchor_confidence,
    )


def _build_advisory_patch(
    index: int,
    anchored: AnchoredFinding,
    decision: GateDecision,
) -> dict[str, Any]:
    finding = anchored.finding
    candidate = _first_candidate(finding)
    risk_level = str(candidate.get("risk", "unknown"))
    patch = {
        "id": f"P{index:03d}",
        "finding_id": finding["id"],
        "source_ref": deepcopy(finding["source_ref"]),
        "patch_category": _infer_patch_category(finding, candidate),
        "strategy": str(candidate.get("strategy", "advisory-review")),
        "recommendation": {
            "suggested_locations": _suggested_locations(anchored.effective_anchor, finding),
            "idea": _recommendation_idea(finding, candidate),
            "risk": risk_level,
        },
        "files_touched": [],
        "files_touched_policy": {
            "allowed": False,
            "reason": "B1 produces advisory-only output and does not generate patches.",
            "risk": "no-runtime-write",
        },
        "expected_impact": {
            "level": str(candidate.get("expected_impact", "unknown")),
            "confidence": float(candidate.get("confidence", finding.get("confidence", 0.0))),
        },
        "measured_impact": None,
        "side_effects": {
            "known": [],
            "unknowns": ["No patch was generated or validated in B1."],
        },
        "risk": {
            "level": risk_level,
            "notes": "Advisory-only; implementation and validation are deferred.",
        },
        "rationale": (
            f"{finding.get('diagnosis', finding.get('title', finding['id']))} "
            f"Gate reason: {decision.reason}."
        ),
        "verification_plan": {
            "build_cmd": None,
            "test_cmd": None,
            "benchmark_cmd": None,
            "manual_steps": ["Review the finding and anchor before implementing a patch."],
            "required": True,
        },
        "status": "advisory-only",
        "validation_status": "not-run",
    }
    if anchored.effective_anchor is not None:
        patch["chosen_anchor"] = anchored.effective_anchor
    return patch


def _first_candidate(finding: dict[str, Any]) -> dict[str, Any]:
    candidates = finding.get("candidate_optimizations", [])
    if isinstance(candidates, list) and candidates:
        candidate = candidates[0]
        if isinstance(candidate, dict):
            return candidate
    return {}


def _infer_patch_category(finding: dict[str, Any], candidate: dict[str, Any]) -> str:
    strategy = str(candidate.get("strategy", "")).lower()
    if "allocation" in strategy:
        return "allocation-reduction"
    kind = finding.get("kind")
    if kind in {"binary-size-large", "binary-size-regression"}:
        return "build-flag"
    if kind in {"benchmark-regression", "benchmark-latency"}:
        return "local-micro-optimization"
    return "local-micro-optimization"


def _suggested_locations(
    effective_anchor: dict[str, Any] | None,
    finding: dict[str, Any],
) -> list[str]:
    if effective_anchor is not None and effective_anchor.get("file"):
        location = str(effective_anchor["file"])
        line_start = effective_anchor.get("line_start")
        if isinstance(line_start, int):
            location = f"{location}:{line_start}"
        return [location]

    source_ref = finding.get("source_ref", {})
    label = source_ref.get("label") if isinstance(source_ref, dict) else None
    if label:
        return [str(label)]
    return []


def _recommendation_idea(finding: dict[str, Any], candidate: dict[str, Any]) -> str:
    title = str(finding.get("title", finding["id"]))
    diagnosis = str(finding.get("diagnosis", "Review the finding before changing code."))
    strategy = candidate.get("strategy")
    if strategy:
        return f"{title}: consider {strategy}. {diagnosis}"
    return f"{title}: review and plan a targeted optimization. {diagnosis}"


def _count_by_key(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _anchor_confidence_distribution(
    anchored_findings: list[AnchoredFinding],
) -> dict[str, int]:
    buckets = {"none": 0, "lt-0.70": 0, "gte-0.70": 0}
    for anchored in anchored_findings:
        confidence = anchored.anchor_confidence
        if confidence is None:
            buckets["none"] += 1
        elif confidence < ANCHOR_GATE_THRESHOLD:
            buckets["lt-0.70"] += 1
        else:
            buckets["gte-0.70"] += 1
    return buckets


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _google_benchmark_entries(document: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        raise ValueError("Google Benchmark report must be a JSON object")
    benchmarks = document.get("benchmarks")
    if not isinstance(benchmarks, list) or not benchmarks:
        raise ValueError("Google Benchmark report must contain a non-empty benchmarks array")

    entries = []
    for benchmark in benchmarks:
        if not isinstance(benchmark, dict):
            continue
        if benchmark.get("run_type") == "aggregate":
            continue
        if not benchmark.get("name"):
            continue
        if "real_time" not in benchmark and "cpu_time" not in benchmark:
            continue
        entries.append(benchmark)
    if not entries:
        raise ValueError("Google Benchmark report has no concrete benchmark entries")
    return entries


def _benchmark_latency_ms(benchmark: dict[str, Any]) -> float:
    value = benchmark.get("real_time", benchmark.get("cpu_time"))
    if not isinstance(value, int | float):
        raise ValueError(f"benchmark {benchmark.get('name')!r} has no numeric time")
    unit = str(benchmark.get("time_unit", "ns"))
    scale = {
        "ns": 0.000001,
        "us": 0.001,
        "ms": 1.0,
        "s": 1000.0,
    }.get(unit)
    if scale is None:
        raise ValueError(f"unsupported Google Benchmark time_unit: {unit}")
    return float(value) * scale


def _baseline_name_for(current_name: str, renamed_map: dict[str, str]) -> str:
    if current_name in renamed_map:
        return renamed_map[current_name]
    for baseline_name, mapped_current in renamed_map.items():
        if mapped_current == current_name:
            return baseline_name
    return current_name


def _build_benchmark_regression_finding(
    *,
    index: int,
    name: str,
    baseline_name: str,
    current_ms: float,
    baseline_ms: float,
    current_path: Path,
    baseline_path: Path | None,
) -> dict[str, Any]:
    if baseline_ms == 0:
        raise ValueError(f"baseline benchmark {baseline_name!r} has zero latency")
    delta_ms = current_ms - baseline_ms
    delta_pct = (delta_ms / baseline_ms) * 100.0
    direction = "increase" if delta_ms >= 0 else "decrease"
    return {
        "id": f"F{index:03d}",
        "kind": "benchmark-regression",
        "title": f"{name} changed by {delta_pct:.1f}%",
        "source_ref": {
            "source_id": "S1",
            "locator": f"$.benchmarks[{index - 1}]",
            "label": name,
        },
        "ownership": "owned",
        "actionability": "actionable",
        "evidence": {
            "metric": "regression_pct",
            "value": round(delta_pct, 6),
            "unit": "percent",
            "baseline": {
                "value": round(baseline_ms, 6),
                "label": str(baseline_path) if baseline_path is not None else baseline_name,
            },
            "delta": {
                "abs": round(abs(delta_ms), 6),
                "pct": round(delta_pct, 6),
                "direction": direction,
            },
            "current": {
                "value": round(current_ms, 6),
                "label": str(current_path),
            },
            "baseline_name": baseline_name,
        },
        "diagnosis": "Google Benchmark before/after comparison changed latency.",
        "confidence": 0.90,
    }


def _build_benchmark_latency_finding(
    *,
    index: int,
    name: str,
    current_ms: float,
) -> dict[str, Any]:
    return {
        "id": f"F{index:03d}",
        "kind": "benchmark-latency",
        "title": f"{name} latency sample",
        "source_ref": {
            "source_id": "S1",
            "locator": f"$.benchmarks[{index - 1}]",
            "label": name,
        },
        "ownership": "owned",
        "actionability": "actionable",
        "evidence": {
            "metric": "latency_ms",
            "value": round(current_ms, 6),
            "unit": "ms",
        },
        "diagnosis": "Single Google Benchmark report; no baseline comparison is available.",
        "confidence": 0.90,
    }


def _aggregate_folded_leaf_samples(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            stack, count_text = line.rsplit(maxsplit=1)
        except ValueError as exc:
            raise ValueError(f"invalid folded stack line {line_number}: {raw_line!r}") from exc
        try:
            samples = int(count_text)
        except ValueError as exc:
            raise ValueError(
                f"invalid folded stack sample count on line {line_number}: {count_text!r}"
            ) from exc
        if samples <= 0:
            raise ValueError(
                f"folded stack sample count must be positive on line {line_number}"
            )
        frames = [frame.strip() for frame in stack.split(";") if frame.strip()]
        if not frames:
            raise ValueError(f"invalid folded stack frames on line {line_number}")
        symbol = frames[-1]
        counts[symbol] = counts.get(symbol, 0) + samples
    if not counts:
        raise ValueError("folded stacks report is empty")
    return counts


def _generic_llm_anchor_can_continue(anchor: dict[str, Any] | None) -> bool:
    if anchor is None:
        return False
    return (
        anchor.get("resolution_method") in {"dwarf", "addr2line", "ctags", "compile-db"}
        and isinstance(anchor.get("anchor_confidence"), int | float)
        and float(anchor["anchor_confidence"]) >= ANCHOR_GATE_THRESHOLD
    )


def _repo_anchors_for_finding(finding: dict[str, Any], repo_root: Path) -> list[dict[str, Any]]:
    if finding.get("source_format") == "generic-llm":
        for symbol in _symbol_candidates(finding):
            anchor = _source_symbol_anchor(symbol, repo_root)
            if anchor is not None:
                return [anchor]

    if finding.get("kind") in {"benchmark-regression", "benchmark-latency"}:
        label = _source_ref_label(finding)
        if label:
            anchor = _benchmark_name_anchor(label, repo_root)
            if anchor is not None:
                return [anchor]

    for symbol in _symbol_candidates(finding):
        anchor = _source_symbol_anchor(symbol, repo_root)
        if anchor is not None:
            return [anchor]
    return []


def _symbol_candidates(finding: dict[str, Any]) -> list[str]:
    candidates = []
    evidence = finding.get("evidence", {})
    if isinstance(evidence, dict):
        hot_symbol = evidence.get("hot_symbol")
        if isinstance(hot_symbol, dict) and hot_symbol.get("symbol"):
            candidates.append(str(hot_symbol["symbol"]))
    for anchor in finding.get("code_anchors", []) or []:
        if isinstance(anchor, dict) and anchor.get("symbol"):
            candidates.append(str(anchor["symbol"]))
    label = _source_ref_label(finding)
    if label and finding.get("kind") == "function-hotspot":
        candidates.append(label)

    deduped = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _source_ref_label(finding: dict[str, Any]) -> str | None:
    source_ref = finding.get("source_ref", {})
    if isinstance(source_ref, dict) and source_ref.get("label"):
        return str(source_ref["label"])
    return None


def _source_symbol_anchor(symbol: str, repo_root: Path) -> dict[str, Any] | None:
    return (
        _anchor_from_tags_file(symbol, repo_root)
        or _anchor_from_compile_db(symbol, repo_root)
        or _anchor_from_grep(symbol, repo_root)
    )


def _anchor_from_tags_file(symbol: str, repo_root: Path) -> dict[str, Any] | None:
    tags_path = repo_root / "tags"
    if not tags_path.exists():
        return None
    for line in tags_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("!"):
            continue
        fields = line.split("\t")
        if len(fields) < 2 or fields[0] != symbol:
            continue
        source_path = repo_root / fields[1]
        location = _find_symbol_in_file(symbol, source_path)
        if location is None:
            continue
        return _code_anchor(
            symbol=symbol,
            repo_root=repo_root,
            source_path=source_path,
            line_start=location,
            resolution_method="ctags",
            confidence=0.75,
            evidence="tags file maps symbol to a unique source file.",
        )
    return None


def _anchor_from_compile_db(symbol: str, repo_root: Path) -> dict[str, Any] | None:
    compile_db_path = repo_root / "compile_commands.json"
    if not compile_db_path.exists():
        return None
    try:
        compile_db = json.loads(compile_db_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(compile_db, list):
        return None
    files = []
    for entry in compile_db:
        if not isinstance(entry, dict) or not entry.get("file"):
            continue
        source_path = Path(str(entry["file"]))
        if not source_path.is_absolute():
            source_path = Path(str(entry.get("directory", repo_root))) / source_path
        files.append(source_path)
    matches = _find_symbol_matches(symbol, files)
    if len(matches) != 1:
        return None
    source_path, line_start = matches[0]
    return _code_anchor(
        symbol=symbol,
        repo_root=repo_root,
        source_path=source_path,
        line_start=line_start,
        resolution_method="compile-db",
        confidence=0.75,
        evidence="compile_commands.json scoped symbol search found one source match.",
    )


def _anchor_from_grep(symbol: str, repo_root: Path) -> dict[str, Any] | None:
    matches = _find_symbol_matches(symbol, _source_files(repo_root))
    if len(matches) != 1:
        return None
    source_path, line_start = matches[0]
    return _code_anchor(
        symbol=symbol,
        repo_root=repo_root,
        source_path=source_path,
        line_start=line_start,
        resolution_method="grep",
        confidence=0.65,
        evidence="repo-root grep found one source match.",
    )


def _benchmark_name_anchor(name: str, repo_root: Path) -> dict[str, Any] | None:
    candidates = _benchmark_name_candidates(name)
    for source_path in _source_files(repo_root):
        try:
            lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            if any(candidate in line for candidate in candidates):
                return _code_anchor(
                    symbol=_benchmark_symbol(name),
                    repo_root=repo_root,
                    source_path=source_path,
                    line_start=line_number,
                    resolution_method="bench-name-map",
                    confidence=0.50,
                    evidence=f"benchmark name {name!r} matched source text.",
                )
    return None


def _benchmark_name_candidates(name: str) -> list[str]:
    symbol = _benchmark_symbol(name)
    candidates = [name, symbol]
    if symbol.startswith("BM_"):
        candidates.append(symbol[3:])
    deduped = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _benchmark_symbol(name: str) -> str:
    return name.split("/", 1)[0]


def _find_symbol_matches(symbol: str, files: list[Path]) -> list[tuple[Path, int]]:
    matches = []
    seen = set()
    for source_path in files:
        key = source_path.resolve() if source_path.exists() else source_path
        if key in seen:
            continue
        seen.add(key)
        line_start = _find_symbol_in_file(symbol, source_path)
        if line_start is not None:
            matches.append((source_path, line_start))
    return matches


def _find_symbol_in_file(symbol: str, source_path: Path) -> int | None:
    if not source_path.exists() or not source_path.is_file():
        return None
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    try:
        lines = source_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None
    for line_number, line in enumerate(lines, start=1):
        if pattern.search(line):
            return line_number
    return None


def _source_files(repo_root: Path) -> list[Path]:
    extensions = {
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hh",
        ".hpp",
        ".hxx",
        ".rs",
    }
    ignored_parts = {".git", ".venv", "build", "out", "__pycache__"}
    files = []
    for path in repo_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if any(part in ignored_parts for part in path.relative_to(repo_root).parts):
            continue
        files.append(path)
    return files


def _code_anchor(
    *,
    symbol: str,
    repo_root: Path,
    source_path: Path,
    line_start: int,
    resolution_method: str,
    confidence: float,
    evidence: str,
) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "file": _repo_relative_path(repo_root, source_path),
        "line_start": line_start,
        "line_end": line_start,
        "language": _language_for_path(source_path),
        "anchor_confidence": confidence,
        "resolution_method": resolution_method,
        "evidence": evidence,
    }


def _repo_relative_path(repo_root: Path, source_path: Path) -> str:
    try:
        return str(source_path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(source_path)


def _language_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".rs":
        return "rust"
    if suffix in {".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx"}:
        return "c++"
    return "c"


def _has_equivalent_anchor(existing: list[dict[str, Any]], anchor: dict[str, Any]) -> bool:
    return any(
        candidate.get("file") == anchor.get("file")
        and candidate.get("line_start") == anchor.get("line_start")
        and candidate.get("symbol") == anchor.get("symbol")
        and candidate.get("resolution_method") == anchor.get("resolution_method")
        for candidate in existing
    )


def _set_generic_default_actionability(finding: dict[str, Any]) -> None:
    if finding.get("actionability") is not None:
        return
    if finding.get("kind") == "function-hotspot":
        has_code_anchor = bool(finding.get("code_anchors"))
        has_attribution_anchor = isinstance(finding.get("attribution_anchor"), dict)
        if has_code_anchor:
            finding.setdefault("ownership", "owned")
            finding["actionability"] = "actionable"
        elif has_attribution_anchor:
            finding.setdefault("ownership", "third-party")
            finding["actionability"] = "actionable"
        else:
            finding.setdefault("ownership", "unknown")
            finding["actionability"] = "informational"
        return
    finding["actionability"] = "actionable"


def _generic_report_id(report_path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", report_path.stem).strip("-") or "report"
    digest = hashlib.sha256(str(report_path).encode("utf-8")).hexdigest()[:10]
    return f"{stem}-{digest}"


def _generic_llm_prompt(
    *,
    raw_text: str,
    raw_path: Path,
    normalized_output: Path,
    repo_root: str | Path | None,
    target_name: str | None,
) -> str:
    repo_root_text = str(repo_root) if repo_root is not None else "<unknown>"
    target_name_text = target_name or raw_path.stem
    return (
        "# Normalize Free-form Performance Report\n\n"
        "You are the host Agent. Read the raw report and write exactly one "
        "canonical performance-findings JSON document.\n\n"
        "Rules:\n"
        "- Do not invent measured impact.\n"
        "- Use schema_version \"1.0\".\n"
        "- Set source_reports[0].source_format to \"generic-llm\".\n"
        "- Set source_reports[0].parser to \"generic-llm\".\n"
        "- Set source_reports[0].confidence to 0.30.\n"
        "- Keep findings[].confidence at or below 0.30 unless deterministic "
        "evidence is present in the raw report.\n"
        "- Prefer advisory-safe findings when symbols, baselines, or anchors are missing.\n"
        "- Write the JSON to this path:\n"
        f"  {normalized_output}\n\n"
        "Context:\n"
        f"- raw_report: {raw_path}\n"
        f"- repo_root: {repo_root_text}\n"
        f"- target_name: {target_name_text}\n\n"
        "Minimum top-level fields:\n"
        "`schema_version`, `report_types`, `target`, `source_reports`, "
        "`run_context`, `findings`, `provenance`.\n\n"
        "Raw report:\n\n"
        "```text\n"
        f"{raw_text}\n"
        "```\n"
    )


def _derive_report_types(findings: Any) -> list[str]:
    kind_to_report_type = {
        "function-hotspot": "hotspot-profile",
        "binary-size-large": "binary-size",
        "binary-size-regression": "binary-size",
        "benchmark-regression": "benchmark",
        "benchmark-latency": "benchmark",
    }
    if not isinstance(findings, list):
        return []
    report_types = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        report_type = kind_to_report_type.get(finding.get("kind"))
        if report_type is not None and report_type not in report_types:
            report_types.append(report_type)
    return report_types
