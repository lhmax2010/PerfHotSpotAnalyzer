from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cli.perf_hotspot_analyzer import main as analyzer_main
from common.schema_validate import PERFORMANCE_FINDINGS, validate_document


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "golden" / "live-perf" / "binary-size"
BIN = FIXTURE / "bin"
OWNERSHIP = FIXTURE / ".perf-skill" / "ownership.yaml"


def test_a2_binary_size_large_topn_e2e(tmp_path: Path) -> None:
    output = tmp_path / "large"
    elf = BIN / "topn.elf"

    assert analyzer_main(
        [
            "binary-size",
            "--elf",
            str(elf),
            "--repo-root",
            str(FIXTURE),
            "--ownership",
            str(OWNERSHIP),
            "--output-dir",
            str(output),
        ]
    ) == 0

    document = json.loads((output / "performance-findings.json").read_text(encoding="utf-8"))
    validate_document(document, document_type=PERFORMANCE_FINDINGS)
    findings = document["findings"]

    assert len(findings) == 5
    assert {finding["kind"] for finding in findings} == {"binary-size-large"}
    assert {finding["evidence"]["threshold"]["type"] for finding in findings} == {"top-n"}
    assert {finding["actionability"] for finding in findings} == {"informational"}
    assert document["report_types"] == ["binary-size"]

    size_map = read_size_sections(elf)
    first = findings[0]
    assert first["evidence"]["value"] == size_map[first["evidence"]["section"]]


def test_a2_binary_size_regression_e2e(tmp_path: Path) -> None:
    output = tmp_path / "regression"
    current = BIN / "after.elf"
    baseline = BIN / "before.elf"

    assert analyzer_main(
        [
            "binary-size",
            "--elf",
            str(current),
            "--baseline",
            str(baseline),
            "--repo-root",
            str(FIXTURE),
            "--ownership",
            str(OWNERSHIP),
            "--output-dir",
            str(output),
        ]
    ) == 0

    document = json.loads((output / "performance-findings.json").read_text(encoding="utf-8"))
    validate_document(document, document_type=PERFORMANCE_FINDINGS)

    assert document["comparison"]["baseline_report"] == str(baseline)
    finding = document["findings"][0]
    assert finding["kind"] == "binary-size-regression"
    assert finding["evidence"]["section"] == ".inflate"
    assert finding["actionability"] == "actionable"
    assert finding["ownership"] == "owned"
    assert finding["evidence"]["delta"] == {
        "abs": 6144,
        "pct": 300.0,
        "direction": "increase",
    }

    current_size = read_size_sections(current)[".inflate"]
    baseline_size = read_size_sections(baseline)[".inflate"]
    assert finding["evidence"]["value"] == current_size
    assert finding["evidence"]["baseline"]["value"] == baseline_size
    assert finding["evidence"]["delta"]["abs"] == current_size - baseline_size

    run_report = json.loads((output / "run-report.json").read_text(encoding="utf-8"))
    assert run_report["findings"]["by_kind"] == {"binary-size-regression": 1}
    assert run_report["gate_decisions"][0]["decision"] == "actionable"


def read_size_sections(path: Path) -> dict[str, int]:
    result = subprocess.run(
        ["size", "-A", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    sections: dict[str, int] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("."):
            sections[parts[0]] = int(parts[1])
    return sections
