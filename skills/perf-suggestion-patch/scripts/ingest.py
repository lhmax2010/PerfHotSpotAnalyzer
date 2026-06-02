"""Analyzer-json ingestion for the perf suggestion patch skill."""

from __future__ import annotations

import json
import time
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
