from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from common.schema_validate import PERFORMANCE_FINDINGS, validate_document


ROOT = Path(__file__).resolve().parents[2]
BUILD_REPORT_PATH = (
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "build_report.py"
)


def load_build_report_module():
    spec = importlib.util.spec_from_file_location("a1_build_report", BUILD_REPORT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sample_analysis(tmp_path: Path) -> dict:
    return {
        "schema_version": "postprocess/v1",
        "bundle_dir": str(tmp_path / "bundle"),
        "source_report": {
            "id": "perf-script",
            "path": "perf-script.txt",
            "source_format": "perf-script",
            "parser": "perf-script-callgraph",
            "confidence": 0.95,
        },
        "target": {
            "kind": "command",
            "pid": None,
            "cmdline": "./slow-loop",
            "service": None,
            "commit": "abc123",
        },
        "profiling": {
            "tool": "perf",
            "events": ["cycles"],
            "callgraph_mode": "fp",
            "artifacts": {"perf_script": "perf-script.txt"},
        },
        "run_context": {
            "cpu_governor": "performance",
            "affinity": "0-3",
            "thermal_state": "unknown",
            "repeat_count": 1,
            "warmup_count": 0,
        },
        "hotspots": [
            {
                "id": "H001",
                "rank": 1,
                "samples": 3,
                "self_cpu_pct": 75.0,
                "hot_frame": {
                    "symbol": "busy_loop",
                    "dso": "/tmp/x86-hotspot/slow-loop",
                    "ownership": "owned",
                },
                "callers": ["main"],
                "ownership": "owned",
                "actionability": "actionable",
                "actionability_reason": "owned hotspot resolved to source",
                "code_anchor": {
                    "symbol": "busy_loop",
                    "dso": "/tmp/x86-hotspot/slow-loop",
                    "file": "src/slow_loop.c",
                    "line_start": 4,
                    "line_end": 4,
                    "language": "c",
                    "anchor_confidence": 0.75,
                    "resolution_method": "ctags",
                    "evidence": "unique source match",
                },
                "bottleneck_class": [],
            },
            {
                "id": "H002",
                "rank": 2,
                "samples": 1,
                "self_cpu_pct": 25.0,
                "hot_frame": {
                    "symbol": "g_signal_emit",
                    "dso": "/usr/lib64/libgobject-2.0.so.0",
                    "ownership": "third-party",
                },
                "callers": ["my_element_chain"],
                "ownership": "third-party",
                "actionability": "actionable",
                "actionability_reason": "owned attribution frame resolved",
                "attribution_anchor": {
                    "symbol": "my_element_chain",
                    "dso": "/usr/lib64/myplugin/libdemo-plugin.so",
                    "file": "src/element.c",
                    "line_start": 8,
                    "line_end": 8,
                    "language": "c",
                    "anchor_confidence": 0.8,
                    "resolution_method": "caller-attribution",
                    "evidence": "owned caller",
                },
                "bottleneck_class": ["external-call-overhead"],
            },
        ],
        "ownership_decisions": [],
    }


def test_build_performance_findings_validates_schema(tmp_path: Path) -> None:
    build_report = load_build_report_module()

    document = build_report.build_performance_findings(
        sample_analysis(tmp_path),
        repo_root=tmp_path,
    )

    validate_document(document, document_type=PERFORMANCE_FINDINGS)
    assert document["report_types"] == ["hotspot-profile"]
    assert document["source_reports"][0]["source_format"] == "perf-script"
    assert "diagnosis" not in document["findings"][0]
    assert document["findings"][1]["attribution_anchor"]["resolution_method"] == "caller-attribution"


def test_build_report_writes_json_markdown_and_run_report(tmp_path: Path) -> None:
    build_report = load_build_report_module()
    analysis_path = tmp_path / "postprocess.json"
    analysis_path.write_text(json.dumps(sample_analysis(tmp_path)), encoding="utf-8")
    output = tmp_path / "out"

    document = build_report.build_report(
        analysis_path=analysis_path,
        output_dir=output,
        repo_root=tmp_path,
    )

    assert json.loads((output / "performance-findings.json").read_text(encoding="utf-8")) == document
    markdown = (output / "analysis-report.md").read_text(encoding="utf-8")
    assert "pending" in markdown
    run_report = json.loads((output / "run-report.json").read_text(encoding="utf-8"))
    assert len(run_report["gate_decisions"]) == 2
    assert run_report["gate_decisions"][0]["reason"] == "owned hotspot resolved to source"


def test_cli_report_keeps_report_run_report(tmp_path: Path) -> None:
    from cli.perf_hotspot_analyzer import main

    analysis_path = tmp_path / "postprocess.json"
    analysis_path.write_text(json.dumps(sample_analysis(tmp_path)), encoding="utf-8")
    output = tmp_path / "cli-out"

    assert main(
        [
            "report",
            "--analysis",
            str(analysis_path),
            "--repo-root",
            str(tmp_path),
            "--output-dir",
            str(output),
        ]
    ) == 0

    run_report = json.loads((output / "run-report.json").read_text(encoding="utf-8"))
    assert run_report["findings"]["total"] == 2
    assert run_report["gate_decisions"][1]["decision"] == "actionable"
