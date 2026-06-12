from __future__ import annotations

import json
from pathlib import Path

from cli.perf_optimization_pipeline import main as pipeline_main
from common.schema_validate import PERFORMANCE_FINDINGS, SUGGESTION_PATCH, validate_document


ROOT = Path(__file__).resolve().parents[2]
X86_FIXTURE = ROOT / "tests" / "fixtures" / "golden" / "live-perf" / "x86-hotspot"
TIZEN_FIXTURE = ROOT / "tests" / "fixtures" / "golden" / "live-perf" / "tizen-arm"
MIXED_FINDINGS = (
    ROOT
    / "tests"
    / "fixtures"
    / "golden"
    / "positive"
    / "01-hotspot-binary-size-mixed"
    / "performance-findings.json"
)


def test_mfinal_full_mode_runs_a_gate_b_gate_and_merged_report(tmp_path: Path) -> None:
    config = tmp_path / "full.yaml"
    config.write_text(
        f"""
        mode: full
        run_id: full
        repo_root: {ROOT}
        output_dir: {tmp_path / "runs"}
        non_interactive: true
        a:
          bundle_dir: tests/fixtures/golden/live-perf/x86-hotspot/bundle
          ownership: tests/fixtures/golden/live-perf/x86-hotspot/.perf-skill/ownership.yaml
        b:
          format: analyzer-json
          repo_root: {ROOT}
        """,
        encoding="utf-8",
    )

    assert pipeline_main(["pipeline", "run", "--config", str(config), "--non-interactive"]) == 0

    run_dir = tmp_path / "runs" / "full"
    findings = json.loads((run_dir / "a_report" / "performance-findings.json").read_text())
    patches = json.loads((run_dir / "b_run" / "patches.json").read_text())
    validate_document(findings, document_type=PERFORMANCE_FINDINGS)
    validate_document(patches, document_type=SUGGESTION_PATCH)

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["gates"]["gate_findings_review"]["status"] == "pass"
    assert state["gates"]["gate_patch_approval"]["status"] == "pass"
    merged = (run_dir / "merged-report.md").read_text(encoding="utf-8")
    assert "Findings: 4" in merged
    assert "Patches: 4" in merged
    assert "The workflow did not apply, commit, or push generated patches." in merged


def test_mfinal_b_only_mode_runs_b_and_gate2(tmp_path: Path) -> None:
    config = tmp_path / "b-only.yaml"
    config.write_text(
        f"""
        mode: b-only
        run_id: b-only
        repo_root: {ROOT}
        output_dir: {tmp_path / "runs"}
        non_interactive: true
        b:
          input: {MIXED_FINDINGS}
          format: analyzer-json
          repo_root: {ROOT}
        """,
        encoding="utf-8",
    )

    assert pipeline_main(["pipeline", "run", "--config", str(config), "--non-interactive"]) == 0

    run_dir = tmp_path / "runs" / "b-only"
    patches = json.loads((run_dir / "b_run" / "patches.json").read_text())
    validate_document(patches, document_type=SUGGESTION_PATCH)
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert "gate_findings_review" not in state["gates"]
    assert state["gates"]["gate_patch_approval"]["status"] == "pass"
    assert not (run_dir / "a_report").exists()


def test_mfinal_a_only_mode_runs_a_without_b(tmp_path: Path) -> None:
    config = tmp_path / "a-only.yaml"
    config.write_text(
        f"""
        mode: a-only
        run_id: a-only
        repo_root: {ROOT}
        output_dir: {tmp_path / "runs"}
        non_interactive: true
        a:
          bundle_dir: tests/fixtures/golden/live-perf/tizen-arm/bundle
          ownership: tests/fixtures/golden/live-perf/tizen-arm/.perf-skill/ownership.yaml
        """,
        encoding="utf-8",
    )

    assert pipeline_main(["pipeline", "run", "--config", str(config), "--non-interactive"]) == 0

    run_dir = tmp_path / "runs" / "a-only"
    document = json.loads((run_dir / "a_report" / "performance-findings.json").read_text())
    validate_document(document, document_type=PERFORMANCE_FINDINGS)
    assert document["target"]["platform"]["os"] == "tizen"
    assert not (run_dir / "b_run").exists()
    merged = (run_dir / "merged-report.md").read_text(encoding="utf-8")
    assert "Patch report is not available for this mode." in merged
