from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_PATH = (
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "preflight.py"
)


def load_preflight_module():
    spec = importlib.util.spec_from_file_location("a1_preflight", PREFLIGHT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_detect_cap_perfmon_reads_effective_capability_bit() -> None:
    preflight = load_preflight_module()

    assert preflight.detect_cap_perfmon(status_text="CapEff:\t0000004000000000\n")
    assert not preflight.detect_cap_perfmon(status_text="CapEff:\t0000000000000000\n")


def test_assess_permissions_accepts_cap_perfmon_without_root() -> None:
    preflight = load_preflight_module()

    result = preflight.assess_permissions(4, True, euid=1000)

    assert result["ok"]
    assert result["reason"] == "CAP_PERFMON present"
    assert result["remediation"] == []


def test_assess_permissions_reports_remediation_for_restrictive_host() -> None:
    preflight = load_preflight_module()

    result = preflight.assess_permissions(4, False, euid=1000)

    assert not result["ok"]
    assert "CAP_PERFMON" in result["reason"]
    assert any("perf_event_paranoid" in item for item in result["remediation"])
    assert any("CAP_PERFMON" in item for item in result["remediation"])


def test_choose_callgraph_auto_prefers_fp_on_x86_when_perf_exists() -> None:
    preflight = load_preflight_module()

    result = preflight.choose_callgraph_mode(
        requested="auto",
        perf_available=True,
        arch="x86_64",
    )

    assert result["mode"] == "fp"
    assert "frame-pointer" in result["reason"]


def test_choose_callgraph_auto_falls_back_to_dwarf_on_non_x86() -> None:
    preflight = load_preflight_module()

    result = preflight.choose_callgraph_mode(
        requested="auto",
        perf_available=True,
        arch="aarch64",
    )

    assert result["mode"] == "dwarf"


def test_choose_callgraph_auto_returns_none_without_perf() -> None:
    preflight = load_preflight_module()

    result = preflight.choose_callgraph_mode(
        requested="auto",
        perf_available=False,
        arch="x86_64",
    )

    assert result["mode"] == "none"
    assert result["reason"] == "perf is unavailable"


def test_run_preflight_composes_json_result(monkeypatch, tmp_path: Path) -> None:
    preflight = load_preflight_module()
    status = tmp_path / "status"
    status.write_text("CapEff:\t0000000000000000\n", encoding="utf-8")
    paranoid = tmp_path / "paranoid"
    paranoid.write_text("1\n", encoding="utf-8")
    monkeypatch.setattr(
        preflight,
        "detect_perf",
        lambda perf_path: {
            "path": perf_path,
            "available": True,
            "version": "perf version 6.8",
            "error": None,
        },
    )

    result = preflight.run_preflight(
        perf_path="/usr/bin/perf",
        requested_callgraph="auto",
        paranoid_path=paranoid,
        status_path=status,
        arch="x86_64",
    )

    assert result["perf"]["version"] == "perf version 6.8"
    assert result["kernel"]["perf_event_paranoid"] == 1
    assert result["kernel"]["permissions_ok"]
    assert result["callgraph"]["mode"] == "fp"


def test_write_preflight_creates_parent_directory(tmp_path: Path) -> None:
    preflight = load_preflight_module()
    output = tmp_path / "nested" / "preflight.json"

    preflight.write_preflight(output, {"schema_version": "preflight/v1"})

    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema_version": "preflight/v1"
    }
