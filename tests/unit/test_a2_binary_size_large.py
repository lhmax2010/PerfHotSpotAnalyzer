from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from common.schema_validate import PERFORMANCE_FINDINGS, validate_document


ROOT = Path(__file__).resolve().parents[2]
BINARY_SIZE_PATH = (
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "binary_size.py"
)


def load_binary_size_module():
    spec = importlib.util.spec_from_file_location("a2_binary_size_large", BINARY_SIZE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_sections(binary_size, sizes: list[int]):
    return [
        binary_size.Section(
            index=index,
            name=f".alloc{index:02d}",
            section_type="PROGBITS",
            address=0x1000 + index,
            offset=0x2000 + index,
            size=size,
            entry_size=0,
            flags="A",
            align=8,
        )
        for index, size in enumerate(sizes, start=1)
    ]


def test_top_n_large_findings_default_to_informational() -> None:
    binary_size = load_binary_size_module()
    sections = make_sections(binary_size, [1000] * 20)

    findings = binary_size.build_large_findings(
        sections=sections,
        elf_path=Path("/tmp/demo.so"),
        source_id="binary-size",
        ownership=binary_size.OwnershipDecision("owned", "owned_paths:/tmp/demo.so"),
    )

    assert len(findings) == 5
    assert {finding["evidence"]["threshold"]["type"] for finding in findings} == {"top-n"}
    assert {finding["actionability"] for finding in findings} == {"informational"}


def test_absolute_threshold_on_owned_binary_is_actionable() -> None:
    binary_size = load_binary_size_module()
    sections = make_sections(binary_size, [70 * 1024, 1000, 1000])

    findings = binary_size.build_large_findings(
        sections=sections,
        elf_path=Path("/tmp/demo.so"),
        source_id="binary-size",
        ownership=binary_size.OwnershipDecision("owned", "owned_paths:/tmp/demo.so"),
    )

    assert findings[0]["evidence"]["threshold"]["type"] == "absolute-bytes"
    assert findings[0]["actionability"] == "actionable"


def test_ratio_threshold_on_unknown_binary_is_downgraded() -> None:
    binary_size = load_binary_size_module()
    sections = make_sections(binary_size, [3000] + [1000] * 20)

    findings = binary_size.build_large_findings(
        sections=sections,
        elf_path=Path("/opt/unknown/demo.so"),
        source_id="binary-size",
        ownership=binary_size.OwnershipDecision("unknown", "no matching ownership rule"),
    )

    assert findings[0]["evidence"]["threshold"]["type"] == "section-ratio"
    assert findings[0]["actionability"] == "informational"
    assert "ownership=unknown" in findings[0]["evidence"]["actionability_reason"]


def test_build_binary_size_document_validates_large_findings(monkeypatch, tmp_path: Path) -> None:
    binary_size = load_binary_size_module()
    elf = tmp_path / "demo.so"
    elf.write_bytes(b"\x7fELF")
    ownership = tmp_path / "ownership.yaml"
    ownership.write_text(f"owned_paths:\n  - {elf}\n", encoding="utf-8")
    monkeypatch.setattr(
        binary_size,
        "read_elf_sections",
        lambda elf_path, readelf="readelf": make_sections(binary_size, [1000] * 20),
    )

    document = binary_size.build_binary_size_document(
        elf_path=elf,
        repo_root=tmp_path,
        ownership_path=ownership,
    )

    validate_document(document, document_type=PERFORMANCE_FINDINGS)
    assert document["report_types"] == ["binary-size"]
    assert document["findings"][0]["kind"] == "binary-size-large"
    assert document["findings"][0]["actionability"] == "informational"


def test_binary_size_outputs_write_contract_files(tmp_path: Path) -> None:
    binary_size = load_binary_size_module()
    document = {
        "schema_version": "1.0",
        "report_types": ["binary-size"],
        "target": {
            "name": "demo.so",
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
                "title": ".alloc01 is in the top 5 allocated sections",
                "source_ref": {"source_id": "binary-size", "locator": "$.sections['.alloc01']", "label": ".alloc01"},
                "actionability": "informational",
                "evidence": {
                    "metric": "section_bytes",
                    "value": 1000,
                    "section": ".alloc01",
                    "file": "demo.so",
                    "threshold": {"type": "top-n", "value": 5, "reason": "top 5 largest allocated sections"},
                },
                "confidence": 0.9,
            }
        ],
        "provenance": {"generated_by": "test", "version": "1.0.0", "timestamp": "2026-06-11T00:00:00Z"},
    }

    binary_size.write_binary_size_outputs(
        document=document,
        output_dir=tmp_path,
        trace_id="trace",
        started_at="2026-06-11T00:00:00Z",
        total_ms=7,
    )

    assert (tmp_path / "performance-findings.json").exists()
    assert "pending" in (tmp_path / "analysis-report.md").read_text(encoding="utf-8")
    run_report = json.loads((tmp_path / "run-report.json").read_text(encoding="utf-8"))
    assert run_report["gate_decisions"][0]["decision"] == "informational"
