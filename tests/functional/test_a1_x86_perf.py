from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cli.perf_hotspot_analyzer import main as analyzer_main
from common.schema_validate import CAPTURE_BUNDLE, PERFORMANCE_FINDINGS, validate_document


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "golden" / "live-perf" / "x86-hotspot"
BUNDLE = FIXTURE / "bundle"


def test_a1_precaptured_bundle_manifest_is_valid() -> None:
    manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))

    validate_document(manifest, document_type=CAPTURE_BUNDLE)

    assert manifest["backend"] == "local"
    assert manifest["perf"]["callgraph_mode"] == "fp"
    for artifact in manifest["artifacts"].values():
        assert (BUNDLE / artifact).exists()


def test_a1_x86_precaptured_analyze_report_chain(tmp_path: Path) -> None:
    analysis_path = tmp_path / "postprocess.json"
    analyze_out = tmp_path / "analyze"
    report_out = tmp_path / "report"

    assert analyzer_main(
        [
            "analyze",
            "--bundle-dir",
            str(BUNDLE),
            "--repo-root",
            str(FIXTURE),
            "--ownership",
            str(FIXTURE / ".perf-skill" / "ownership.yaml"),
            "--output",
            str(analysis_path),
            "--output-dir",
            str(analyze_out),
        ]
    ) == 0
    assert analyzer_main(
        [
            "report",
            "--analysis",
            str(analysis_path),
            "--repo-root",
            str(FIXTURE),
            "--output-dir",
            str(report_out),
        ]
    ) == 0

    document = json.loads((report_out / "performance-findings.json").read_text(encoding="utf-8"))
    validate_document(document, document_type=PERFORMANCE_FINDINGS)

    top = document["findings"][0]
    assert top["evidence"]["hot_symbol"]["symbol"] == "busy_loop"
    assert top["evidence"]["rank"] == 1
    assert top["ownership"] == "owned"
    assert top["actionability"] == "actionable"
    assert top["code_anchors"][0]["file"] == "src/slow_loop.c"
    assert document["profiling"]["callgraph_mode"] == "fp"
    assert document["run_context"]["cpu_governor"] == "performance"

    by_symbol = {
        finding["evidence"]["hot_symbol"]["symbol"]: finding
        for finding in document["findings"]
    }
    assert by_symbol["g_signal_emit"]["actionability"] == "actionable"
    assert by_symbol["g_signal_emit"]["attribution_anchor"]["symbol"] == "busy_loop"
    assert by_symbol["malloc"]["actionability"] == "not-actionable"
    assert by_symbol["mystery_hot"]["actionability"] == "informational"

    run_report = json.loads((report_out / "run-report.json").read_text(encoding="utf-8"))
    assert run_report["findings"]["total"] == 4
    assert len(run_report["gate_decisions"]) == 4


def test_a1_analysis_report_marks_diagnosis_pending(tmp_path: Path) -> None:
    analysis_path = tmp_path / "postprocess.json"
    report_out = tmp_path / "report"
    assert analyzer_main(
        [
            "analyze",
            "--bundle-dir",
            str(BUNDLE),
            "--repo-root",
            str(FIXTURE),
            "--ownership",
            str(FIXTURE / ".perf-skill" / "ownership.yaml"),
            "--output",
            str(analysis_path),
            "--output-dir",
            str(tmp_path / "analyze"),
        ]
    ) == 0
    assert analyzer_main(
        [
            "report",
            "--analysis",
            str(analysis_path),
            "--repo-root",
            str(FIXTURE),
            "--output-dir",
            str(report_out),
        ]
    ) == 0

    markdown = (report_out / "analysis-report.md").read_text(encoding="utf-8")
    assert "## Diagnosis" in markdown
    assert "pending" in markdown


@pytest.mark.skipif(
    os.environ.get("PERF_SKILL_ENABLE_LIVE_PERF") != "1",
    reason="live perf capture is disabled by default in CI",
)
def test_a1_live_perf_capture_smoke(tmp_path: Path) -> None:
    if shutil.which("gcc") is None or shutil.which("perf") is None:
        pytest.skip("gcc and perf are required for live capture")
    binary = tmp_path / "slow-loop"
    subprocess.run(
        ["gcc", "-O2", "-fno-omit-frame-pointer", str(FIXTURE / "src" / "slow_loop.c"), "-o", str(binary)],
        check=True,
    )
    job = tmp_path / "capture-job.yaml"
    job.write_text(
        "\n".join(
            [
                "device: host",
                "target:",
                "  kind: command",
                f"  command: \"{binary} 500000\"",
                "perf:",
                "  events: [cycles]",
                "  freq_hz: 99",
                "  callgraph: auto",
                "  duration_s: 1",
                "  repeat: 1",
                "  warmup: 0",
                "output:",
                "  bundle_name: live-smoke",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    device_dir = tmp_path / ".perf-skill" / "devices"
    device_dir.mkdir(parents=True)
    (device_dir / "host.yaml").write_text(
        "\n".join(
            [
                "name: host",
                "backend: local",
                f"remote_workdir: {tmp_path / 'remote'}",
                "perf_path: perf",
                "needs_sudo: false",
                "arch: x86_64",
                "target_has_stackcollapse: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "remote").mkdir()

    assert analyzer_main(
        [
            "capture",
            "--job",
            str(job),
            "--repo-root",
            str(tmp_path),
            "--output-dir",
            str(tmp_path / "captures"),
        ]
    ) == 0

    validate_document(
        json.loads(
            (tmp_path / "captures" / "live-smoke" / "manifest.json").read_text(encoding="utf-8")
        ),
        document_type=CAPTURE_BUNDLE,
    )
