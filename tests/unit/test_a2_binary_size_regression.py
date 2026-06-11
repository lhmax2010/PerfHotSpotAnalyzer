from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from common.schema_validate import PERFORMANCE_FINDINGS, validate_document


ROOT = Path(__file__).resolve().parents[2]
BINARY_SIZE_PATH = (
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "binary_size.py"
)


def load_binary_size_module():
    spec = importlib.util.spec_from_file_location("a2_binary_size_regression", BINARY_SIZE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def section(binary_size, name: str, size: int):
    return binary_size.Section(
        index=1,
        name=name,
        section_type="PROGBITS",
        address=0x1000,
        offset=0x2000,
        size=size,
        entry_size=0,
        flags="A",
        align=8,
    )


def test_regression_finding_triggers_on_five_percent_growth() -> None:
    binary_size = load_binary_size_module()

    findings = binary_size.build_regression_findings(
        current_sections=[section(binary_size, ".text", 1060)],
        baseline_sections=[section(binary_size, ".text", 1000)],
        current_path=Path("after.so"),
        baseline_path=Path("before.so"),
        source_id="binary-size-current",
        ownership=binary_size.OwnershipDecision("owned", "owned_paths:after.so"),
    )

    assert findings[0]["kind"] == "binary-size-regression"
    assert findings[0]["actionability"] == "actionable"
    assert findings[0]["evidence"]["delta"] == {
        "abs": 60,
        "pct": 6.0,
        "direction": "increase",
    }


def test_regression_finding_triggers_on_one_kib_delta_even_below_five_percent() -> None:
    binary_size = load_binary_size_module()

    findings = binary_size.build_regression_findings(
        current_sections=[section(binary_size, ".rodata", 103000)],
        baseline_sections=[section(binary_size, ".rodata", 100000)],
        current_path=Path("after.so"),
        baseline_path=Path("before.so"),
        source_id="binary-size-current",
        ownership=binary_size.OwnershipDecision("owned", "owned_paths:after.so"),
    )

    assert findings[0]["evidence"]["delta"]["abs"] == 3000
    assert findings[0]["evidence"]["delta"]["pct"] == 3.0


def test_regression_records_decrease_direction() -> None:
    binary_size = load_binary_size_module()

    findings = binary_size.build_regression_findings(
        current_sections=[section(binary_size, ".data", 900)],
        baseline_sections=[section(binary_size, ".data", 1000)],
        current_path=Path("after.so"),
        baseline_path=Path("before.so"),
        source_id="binary-size-current",
        ownership=binary_size.OwnershipDecision("owned", "owned_paths:after.so"),
    )

    assert findings[0]["evidence"]["delta"]["direction"] == "decrease"
    assert findings[0]["evidence"]["value"] == 900


def test_new_section_regression_uses_zero_baseline() -> None:
    binary_size = load_binary_size_module()

    findings = binary_size.build_regression_findings(
        current_sections=[section(binary_size, ".newdata", 2048)],
        baseline_sections=[],
        current_path=Path("after.so"),
        baseline_path=Path("before.so"),
        source_id="binary-size-current",
        ownership=binary_size.OwnershipDecision("owned", "owned_paths:after.so"),
    )

    assert findings[0]["evidence"]["baseline"]["value"] == 0
    assert findings[0]["evidence"]["delta"]["pct"] == 100.0


def test_regression_unknown_ownership_downgrades_to_informational() -> None:
    binary_size = load_binary_size_module()

    findings = binary_size.build_regression_findings(
        current_sections=[section(binary_size, ".text", 4096)],
        baseline_sections=[section(binary_size, ".text", 1024)],
        current_path=Path("/opt/unknown/after.so"),
        baseline_path=Path("before.so"),
        source_id="binary-size-current",
        ownership=binary_size.OwnershipDecision("unknown", "no matching ownership rule"),
    )

    assert findings[0]["actionability"] == "informational"
    assert "ownership=unknown" in findings[0]["evidence"]["actionability_reason"]


def test_build_binary_size_document_validates_regression(monkeypatch, tmp_path: Path) -> None:
    binary_size = load_binary_size_module()
    before = tmp_path / "before.so"
    after = tmp_path / "after.so"
    before.write_bytes(b"\x7fELF")
    after.write_bytes(b"\x7fELF")
    ownership = tmp_path / "ownership.yaml"
    ownership.write_text(f"owned_paths:\n  - {after}\n", encoding="utf-8")

    def fake_read_elf_sections(path, readelf="readelf"):
        if Path(path) == after:
            return [section(binary_size, ".text", 4096)]
        return [section(binary_size, ".text", 2048)]

    monkeypatch.setattr(binary_size, "read_elf_sections", fake_read_elf_sections)

    document = binary_size.build_binary_size_document(
        elf_path=after,
        baseline_path=before,
        repo_root=tmp_path,
        ownership_path=ownership,
    )

    validate_document(document, document_type=PERFORMANCE_FINDINGS)
    assert document["comparison"]["baseline_report"] == str(before)
    assert [source["id"] for source in document["source_reports"]] == [
        "binary-size-current",
        "binary-size-baseline",
    ]
    assert document["findings"][0]["kind"] == "binary-size-regression"
