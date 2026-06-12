"""Build canonical performance-findings reports from postprocess output."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from common import schema_validate
from common.schema_validate import KIND_TO_REPORT_TYPE, PERFORMANCE_FINDINGS
from common.tracing import TraceLogger, start_trace


def build_report(
    *,
    analysis_path: str | Path,
    output_dir: str | Path,
    repo_root: str | Path = ".",
    tracer: TraceLogger | None = None,
) -> dict[str, Any]:
    analysis = _load_json(Path(analysis_path))
    document = build_performance_findings(analysis, repo_root=Path(repo_root))
    schema_validate.validate_document(document, document_type=PERFORMANCE_FINDINGS)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    findings_path = output / "performance-findings.json"
    findings_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown = build_analysis_markdown(document, analysis)
    (output / "analysis-report.md").write_text(markdown, encoding="utf-8")
    run_report = build_run_report(
        trace_id=tracer.trace_id if tracer is not None else "manual",
        started_at=datetime.now(UTC).isoformat(),
        total_ms=0,
        document=document,
        analysis=analysis,
        exit_status="success",
    )
    (output / "run-report.json").write_text(
        json.dumps(run_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if tracer is not None:
        tracer.info("report", "validated", findings=len(document["findings"]))
    return document


def build_performance_findings(
    analysis: Mapping[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    source_report = dict(analysis["source_report"])
    source_report["id"] = str(source_report.get("id") or "perf-script")
    source_report["source_format"] = "perf-script"
    source_report["parser"] = str(source_report.get("parser") or "perf-script-callgraph")
    source_report["confidence"] = float(source_report.get("confidence", 0.95))
    findings = [
        _finding_from_hotspot(hotspot, source_report, index)
        for index, hotspot in enumerate(analysis.get("hotspots", []), start=1)
    ]
    report_types = derive_report_types(findings)
    target = _target_from_analysis(analysis, repo_root)
    document = {
        "schema_version": "1.0",
        "report_types": report_types,
        "target": target,
        "source_reports": [source_report],
        "run_context": _run_context_from_analysis(analysis),
        "profiling": _profiling_from_analysis(analysis),
        "findings": findings,
        "notes": (
            "Diagnosis and candidate_optimizations are pending host Agent review; "
            "A1 scripts do not call LLM APIs."
        ),
        "provenance": {
            "generated_by": "perf-hotspot-analyzer/build_report",
            "version": "1.0.0",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }
    if "tizen" in analysis:
        document["tizen"] = dict(analysis["tizen"])
    return document


def derive_report_types(findings: Sequence[Mapping[str, Any]]) -> list[str]:
    values = {
        KIND_TO_REPORT_TYPE[finding["kind"]]
        for finding in findings
        if finding.get("kind") in KIND_TO_REPORT_TYPE
    }
    return sorted(values)


def build_analysis_markdown(
    document: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> str:
    lines = [
        "# Perf Hotspot Analysis",
        "",
        "## Hotspots",
        "",
        "| Rank | Symbol | Self CPU | Ownership | Actionability | Anchor |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for finding in document["findings"]:
        evidence = finding["evidence"]
        anchor = finding.get("attribution_anchor") or (
            finding.get("code_anchors") or [{}]
        )[0]
        anchor_text = anchor.get("file", "unresolved")
        if anchor.get("line_start"):
            anchor_text = f"{anchor_text}:{anchor['line_start']}"
        lines.append(
            "| {rank} | `{symbol}` | {value:.2f}% | {ownership} | {actionability} | {anchor} |".format(
                rank=evidence["rank"],
                symbol=evidence["hot_symbol"]["symbol"],
                value=evidence["value"],
                ownership=finding.get("ownership", "unknown"),
                actionability=finding.get("actionability", "informational"),
                anchor=anchor_text,
            )
        )
    lines.extend(
        [
            "",
            "## Diagnosis",
            "",
            "pending",
            "",
            "## Artifacts",
            "",
            f"- Capture bundle: `{analysis.get('bundle_dir', '')}`",
            "- Primary symbolization source: `perf-script.txt`",
        ]
    )
    return "\n".join(lines) + "\n"


def build_run_report(
    *,
    trace_id: str,
    started_at: str,
    total_ms: int,
    document: Mapping[str, Any],
    analysis: Mapping[str, Any],
    exit_status: str,
    errors: Sequence[str] = (),
) -> dict[str, Any]:
    findings = document["findings"]
    by_kind: dict[str, int] = {}
    for finding in findings:
        by_kind[finding["kind"]] = by_kind.get(finding["kind"], 0) + 1
    return {
        "schema_version": "run-report/v1",
        "trace_id": trace_id,
        "skill": "perf-hotspot-analyzer",
        "started_at": started_at,
        "total_ms": total_ms,
        "by_step": {"report": total_ms},
        "input": {
            "callgraph_mode": document.get("profiling", {}).get("callgraph_mode"),
            "source_formats": ["perf-script"],
        },
        "findings": {"total": len(findings), "by_kind": by_kind},
        "anchors": _anchor_summary(findings),
        "gate_decisions": [
            {
                "finding": finding["id"],
                "decision": finding.get("actionability", "informational"),
                "reason": _hotspot_reason(analysis, finding["id"]),
            }
            for finding in findings
        ],
        "patches": {"diff-ready": 0, "needs-review": 0, "advisory-only": 0},
        "degradations": [],
        "exit_status": exit_status,
        "errors": list(errors),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build performance-findings.json.")
    parser.add_argument("--analysis", required=True, help="postprocess.json path")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.monotonic()
    tracer = start_trace(
        skill="perf-hotspot-analyzer",
        output_dir=args.output_dir,
        verbose=args.verbose,
    )
    try:
        document = build_report(
            analysis_path=args.analysis,
            output_dir=args.output_dir,
            repo_root=args.repo_root,
            tracer=tracer,
        )
        run_report = build_run_report(
            trace_id=tracer.trace_id,
            started_at=datetime.now(UTC).isoformat(),
            total_ms=int((time.monotonic() - started) * 1000),
            document=document,
            analysis=_load_json(Path(args.analysis)),
            exit_status="success",
        )
        (Path(args.output_dir) / "run-report.json").write_text(
            json.dumps(run_report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    finally:
        tracer.close()
    return 0


def _finding_from_hotspot(
    hotspot: Mapping[str, Any],
    source_report: Mapping[str, Any],
    index: int,
) -> dict[str, Any]:
    hot_frame = hotspot["hot_frame"]
    ownership = hotspot.get("ownership") or hot_frame.get("ownership", "unknown")
    actionability = hotspot.get("actionability", "informational")
    finding = {
        "id": f"F{index:03d}",
        "kind": "function-hotspot",
        "title": f"Hot function {hot_frame['symbol']}",
        "source_ref": {
            "source_id": source_report["id"],
            "locator": f"$.hotspots[{index - 1}]",
            "label": hot_frame["symbol"],
        },
        "ownership": ownership,
        "actionability": actionability,
        "evidence": {
            "metric": "self_cpu_pct",
            "value": float(hotspot["self_cpu_pct"]),
            "unit": "percent",
            "samples": int(hotspot["samples"]),
            "rank": int(hotspot["rank"]),
            "callers": list(hotspot.get("callers", [])),
            "hot_symbol": {
                "symbol": hot_frame["symbol"],
                "dso": hot_frame.get("dso", ""),
                "ownership": ownership,
            },
        },
        "confidence": min(float(source_report.get("confidence", 0.95)), 0.9),
    }
    code_anchor = hotspot.get("code_anchor")
    if isinstance(code_anchor, Mapping):
        finding["code_anchors"] = [dict(code_anchor)]
    attribution_anchor = hotspot.get("attribution_anchor")
    if isinstance(attribution_anchor, Mapping):
        finding["attribution_anchor"] = dict(attribution_anchor)
    bottleneck_class = hotspot.get("bottleneck_class")
    if bottleneck_class:
        finding["bottleneck_class"] = list(bottleneck_class)
    if actionability == "actionable" and ownership == "owned" and "code_anchors" not in finding:
        finding["actionability"] = "informational"
    if (
        actionability == "actionable"
        and ownership != "owned"
        and "attribution_anchor" not in finding
    ):
        finding["actionability"] = "not-actionable"
    return finding


def _target_from_analysis(analysis: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    raw = analysis.get("target", {})
    raw_kind = raw.get("kind")
    kind_map = {"pid": "process", "command": "binary", "service": "service"}
    name = raw.get("service") or raw.get("cmdline") or (
        f"pid-{raw.get('pid')}" if raw.get("pid") else "unknown-target"
    )
    return {
        "name": str(name),
        "kind": kind_map.get(str(raw_kind), "process"),
        "command": str(raw.get("cmdline") or ""),
        "repo_root": str(repo_root),
        "commit": raw.get("commit") or "",
        "platform": {
            "os": "tizen" if "tizen" in analysis else "linux",
            "arch": _arch_from_analysis(analysis),
            "kernel": os.uname().release if hasattr(os, "uname") else "",
        },
    }


def _arch_from_analysis(analysis: Mapping[str, Any]) -> str:
    bundle_manifest = analysis.get("device", {})
    arch = bundle_manifest.get("arch") if isinstance(bundle_manifest, Mapping) else None
    if arch in {"armv7", "aarch64", "x86_64"}:
        return str(arch)
    return "x86_64"


def _run_context_from_analysis(analysis: Mapping[str, Any]) -> dict[str, Any]:
    raw = analysis.get("run_context", {})
    governor = raw.get("cpu_governor", "unknown")
    if governor not in {"performance", "ondemand", "schedutil", "unknown"}:
        governor = "unknown"
    return {
        "device": "host",
        "cpu_governor": governor,
        "core_count": os.cpu_count() or 1,
        "repeat_count": int(raw.get("repeat_count", 1)),
        "warmup_count": int(raw.get("warmup_count", 0)),
    }


def _profiling_from_analysis(analysis: Mapping[str, Any]) -> dict[str, Any]:
    profiling = analysis.get("profiling", {})
    return {
        "tool": "perf",
        "events": list(profiling.get("events", ["cycles"])),
        "callgraph_mode": profiling.get("callgraph_mode", "none"),
        "artifacts": dict(profiling.get("artifacts", {})),
    }


def _anchor_summary(findings: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    buckets = {">=0.9": 0, "0.7-0.9": 0, "<0.7": 0}
    resolved = 0
    for finding in findings:
        anchor = finding.get("attribution_anchor")
        if not anchor:
            anchors = finding.get("code_anchors") or []
            anchor = anchors[0] if anchors else None
        if not anchor:
            continue
        resolved += 1
        confidence = float(anchor.get("anchor_confidence", 0))
        if confidence >= 0.9:
            buckets[">=0.9"] += 1
        elif confidence >= 0.7:
            buckets["0.7-0.9"] += 1
        else:
            buckets["<0.7"] += 1
    return {"resolved": resolved, "confidence_distribution": buckets}


def _hotspot_reason(analysis: Mapping[str, Any], finding_id: str) -> str:
    try:
        index = int(finding_id[1:]) - 1
    except (ValueError, IndexError):
        return "unknown"
    hotspots = analysis.get("hotspots", [])
    if 0 <= index < len(hotspots):
        return str(hotspots[index].get("actionability_reason", "unknown"))
    return "unknown"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
