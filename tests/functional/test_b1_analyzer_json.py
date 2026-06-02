from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from cli.perf_suggestion_patch import main as suggestion_patch_main
from common.schema_validate import SUGGESTION_PATCH, validate_file


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "golden"
INGEST_PATH = ROOT / "skills" / "perf-suggestion-patch" / "scripts" / "ingest.py"


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("b1_ingest_functional", INGEST_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("fixture_name", "expected_reasons"),
    [
        (
            "01-hotspot-binary-size-mixed",
            ["b1-advisory-only", "effective_anchor=null"],
        ),
        ("15-attribution-third-party-owned", ["b1-advisory-only"]),
        ("16-attribution-no-owned-not-actionable", ["actionability=not-actionable"]),
        ("17-effective-anchor-prefers-attribution", ["b1-advisory-only"]),
    ],
)
def test_b1_analyzer_json_e2e_advisory_outputs(
    tmp_path: Path,
    fixture_name: str,
    expected_reasons: list[str],
) -> None:
    ingest = load_ingest_module()
    result = ingest.run_analyzer_json(
        FIXTURE_ROOT / "positive" / fixture_name / "performance-findings.json",
        tmp_path,
    )

    validate_file(result.patches_path, document_type=SUGGESTION_PATCH)
    assert result.suggestion_patch["patches"]
    assert [patch["status"] for patch in result.suggestion_patch["patches"]] == [
        "advisory-only"
    ] * len(result.suggestion_patch["patches"])
    assert [patch["validation_status"] for patch in result.suggestion_patch["patches"]] == [
        "not-run"
    ] * len(result.suggestion_patch["patches"])
    assert all(patch["measured_impact"] is None for patch in result.suggestion_patch["patches"])
    assert all("diff" not in patch for patch in result.suggestion_patch["patches"])

    gate_decisions = result.run_report["gate_decisions"]
    assert len(gate_decisions) == len(result.suggestion_patch["patches"])
    assert [decision["reason"] for decision in gate_decisions] == expected_reasons
    assert result.run_report["patches"]["advisory-only"] == len(gate_decisions)
    assert result.run_report["patches"]["diff-ready"] == 0
    assert result.run_report["patches"]["needs-review"] == 0


def test_b1_attribution_anchor_becomes_effective_anchor(tmp_path: Path) -> None:
    ingest = load_ingest_module()
    result = ingest.run_analyzer_json(
        FIXTURE_ROOT
        / "positive"
        / "17-effective-anchor-prefers-attribution"
        / "performance-findings.json",
        tmp_path,
    )

    decision = result.run_report["gate_decisions"][0]
    assert decision["effective_anchor"]["symbol"] == "owned_emit_many"
    assert decision["effective_anchor"]["file"] == "src/signal_adapter.c"
    assert decision["effective_anchor"]["anchor_confidence"] == 0.80
    assert result.suggestion_patch["patches"][0]["chosen_anchor"]["symbol"] == "owned_emit_many"


def test_b1_fixture_06_advisory_contract_baseline() -> None:
    patch_path = (
        FIXTURE_ROOT / "positive" / "06-advisory-only-patch" / "patches.json"
    )
    document = json.loads(patch_path.read_text(encoding="utf-8"))

    validate_file(patch_path, document_type=SUGGESTION_PATCH)
    assert document["patches"][0]["status"] == "advisory-only"
    assert "diff" not in document["patches"][0]


def test_b1_cli_analyze_writes_outputs(tmp_path: Path) -> None:
    exit_code = suggestion_patch_main(
        [
            "analyze",
            "--input",
            str(
                FIXTURE_ROOT
                / "positive"
                / "01-hotspot-binary-size-mixed"
                / "performance-findings.json"
            ),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "patches.json").exists()
    assert (tmp_path / "run-report.json").exists()


def test_b1_cli_analyze_rejects_invalid_report(tmp_path: Path) -> None:
    exit_code = suggestion_patch_main(
        [
            "analyze",
            "--input",
            str(
                FIXTURE_ROOT
                / "negative"
                / "23-actionable-third-party-missing-attribution"
                / "performance-findings.json"
            ),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 1


def test_b2_cli_analyze_auto_detects_google_benchmark(tmp_path: Path) -> None:
    exit_code = suggestion_patch_main(
        [
            "analyze",
            "--input",
            str(
                FIXTURE_ROOT
                / "positive"
                / "02-google-benchmark-before-after"
                / "after.json"
            ),
            "--baseline-report",
            str(
                FIXTURE_ROOT
                / "positive"
                / "02-google-benchmark-before-after"
                / "before.json"
            ),
            "--repo-root",
            "/repo/demo",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    run_report = json.loads((tmp_path / "run-report.json").read_text(encoding="utf-8"))
    assert run_report["input"]["source_formats"] == ["google-benchmark", "google-benchmark"]
    assert run_report["findings"]["by_kind"] == {"benchmark-regression": 1}


def test_b2_cli_analyze_auto_detects_folded_stacks(tmp_path: Path) -> None:
    exit_code = suggestion_patch_main(
        [
            "analyze",
            "--input",
            str(FIXTURE_ROOT / "positive" / "13-capture-bundle-10-piece" / "out.folded"),
            "--repo-root",
            "/repo/demo",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    run_report = json.loads((tmp_path / "run-report.json").read_text(encoding="utf-8"))
    assert run_report["input"]["source_formats"] == ["folded-stacks"]
    assert run_report["findings"]["by_kind"] == {"function-hotspot": 2}
