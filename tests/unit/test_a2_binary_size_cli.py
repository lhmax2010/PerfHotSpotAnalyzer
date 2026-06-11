from __future__ import annotations

import json
from pathlib import Path

from cli import perf_hotspot_analyzer


class FakeBinarySizeModule:
    def __init__(self) -> None:
        self.calls = []

    def build_binary_size_document(self, **kwargs):
        self.calls.append(("build", kwargs))
        return {
            "schema_version": "1.0",
            "report_types": ["binary-size"],
            "target": {
                "name": Path(kwargs["elf_path"]).name,
                "kind": "binary",
                "platform": {"os": "linux", "arch": "x86_64"},
            },
            "source_reports": [
                {
                    "id": "binary-size",
                    "source_format": "external",
                    "parser": "readelf-section-table",
                    "confidence": 0.95,
                }
            ],
            "run_context": {"device": "host", "repeat_count": 1, "warmup_count": 0},
            "findings": [
                {
                    "id": "F001",
                    "kind": "binary-size-large",
                    "title": ".text is in the top 5 allocated sections",
                    "source_ref": {"source_id": "binary-size", "locator": "$.sections['.text']", "label": ".text"},
                    "actionability": "informational",
                    "evidence": {
                        "metric": "section_bytes",
                        "value": 4096,
                        "section": ".text",
                        "file": str(kwargs["elf_path"]),
                        "threshold": {"type": "top-n", "value": 5, "reason": "top 5 largest allocated sections"},
                    },
                    "confidence": 0.9,
                }
            ],
            "provenance": {"generated_by": "fake", "version": "1.0.0", "timestamp": "2026-06-11T00:00:00Z"},
        }

    def write_binary_size_outputs(self, **kwargs) -> None:
        self.calls.append(("write", kwargs))
        output = Path(kwargs["output_dir"])
        output.mkdir(parents=True, exist_ok=True)
        (output / "performance-findings.json").write_text(
            json.dumps(kwargs["document"]),
            encoding="utf-8",
        )
        (output / "run-report.json").write_text(
            json.dumps({"gate_decisions": [{"decision": "informational"}]}),
            encoding="utf-8",
        )
        (output / "analysis-report.md").write_text("pending\n", encoding="utf-8")


def test_cli_binary_size_passes_current_and_baseline_args(monkeypatch, tmp_path: Path) -> None:
    fake = FakeBinarySizeModule()

    def fake_load_script(name: str):
        assert name == "binary_size"
        return fake

    monkeypatch.setattr(perf_hotspot_analyzer, "_load_script", fake_load_script)
    output = tmp_path / "out"
    current = tmp_path / "after.so"
    baseline = tmp_path / "before.so"
    current.write_bytes(b"\x7fELF")
    baseline.write_bytes(b"\x7fELF")

    exit_code = perf_hotspot_analyzer.main(
        [
            "binary-size",
            "--elf",
            str(current),
            "--baseline",
            str(baseline),
            "--repo-root",
            str(tmp_path),
            "--ownership",
            str(tmp_path / "ownership.yaml"),
            "--user-budget-bytes",
            "2048",
            "--readelf",
            "/usr/bin/readelf",
            "--output-dir",
            str(output),
        ]
    )

    assert exit_code == 0
    build_call = fake.calls[0][1]
    assert build_call["elf_path"] == str(current)
    assert build_call["baseline_path"] == str(baseline)
    assert build_call["user_budget_bytes"] == 2048
    assert build_call["readelf"] == "/usr/bin/readelf"
    assert (output / "performance-findings.json").exists()
