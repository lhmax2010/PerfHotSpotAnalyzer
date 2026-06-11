from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from common.device_runner import DeviceProfile
from common.schema_validate import CAPTURE_BUNDLE, validate_document


ROOT = Path(__file__).resolve().parents[2]
CAPTURE_PATH = ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "capture.py"


def load_capture_module():
    spec = importlib.util.spec_from_file_location("a1_capture", CAPTURE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_capture_job_reads_nested_perf_options(tmp_path: Path) -> None:
    capture = load_capture_module()
    job = tmp_path / "capture-job.yaml"
    job.write_text(
        """
        device: host
        target:
          kind: command
          command: ./slow-loop
        perf:
          events: [cycles]
          freq_hz: 997
          callgraph: auto
          duration_s: 3
          repeat: 2
          warmup: 1
        output:
          bundle_name: bundle-x86.tar.gz
        """,
        encoding="utf-8",
    )

    parsed = capture.load_capture_job(job)

    assert parsed["device"] == "host"
    assert parsed["target"]["command"] == "./slow-loop"
    assert parsed["perf"]["repeat"] == 2


def test_build_runner_command_omits_sudo_and_passes_callgraph(tmp_path: Path) -> None:
    capture = load_capture_module()
    profile = DeviceProfile(
        name="host",
        backend="local",
        arch="x86_64",
        path=tmp_path / "host.yaml",
        remote_workdir=tmp_path,
        perf_path="/usr/bin/perf",
    )
    job = {
        "target": {"kind": "command", "command": "./slow-loop"},
        "perf": {"events": ["cycles"], "freq_hz": 999, "duration_s": 2, "repeat": 1, "warmup": 0},
    }

    command = capture.build_runner_command(
        remote_bundle_dir=tmp_path / "bundle",
        profile=profile,
        job=job,
        callgraph_mode="fp",
    )

    assert "sudo" not in command
    assert "/usr/bin/perf" in command
    assert " fp " in f" {command} "
    assert "./slow-loop" in command


def test_ensure_folded_from_perf_script_collapses_stacks(tmp_path: Path) -> None:
    capture = load_capture_module()
    (tmp_path / "perf-script.txt").write_text(
        """
        slow-loop 1/1 1.0: 0x1 busy_loop /tmp/slow-loop
                  0x2 main /tmp/slow-loop

        slow-loop 1/1 1.1: 0x1 busy_loop /tmp/slow-loop
                  0x2 main /tmp/slow-loop
        """,
        encoding="utf-8",
    )
    (tmp_path / "out.folded").write_text("", encoding="utf-8")

    capture.ensure_folded_from_perf_script(tmp_path)

    assert (tmp_path / "out.folded").read_text(encoding="utf-8").strip() == "main;busy_loop 2"


def test_build_manifest_validates_capture_bundle_schema(tmp_path: Path) -> None:
    capture = load_capture_module()
    for name in [
        "perf.data",
        "perf-script.txt",
        "out.folded",
        "perf-report.txt",
        "kallsyms",
        "dso-list.txt",
        "exec.log",
        "proc-4242-maps",
    ]:
        (tmp_path / name).write_text("fixture\n", encoding="utf-8")
    (tmp_path / "run-context.json").write_text(
        json.dumps(
            {
                "cpu_governor": "performance",
                "affinity": "0-3",
                "thermal_state": "unknown",
            }
        ),
        encoding="utf-8",
    )
    profile = DeviceProfile(
        name="host",
        backend="local",
        arch="x86_64",
        path=tmp_path / "host.yaml",
        remote_workdir=tmp_path,
    )
    job = {
        "target": {"kind": "command", "command": "./slow-loop", "commit": "abc123"},
        "perf": {"events": ["cycles"], "freq_hz": 999, "duration_s": 2, "repeat": 1, "warmup": 0},
    }
    preflight = {
        "callgraph": {"mode": "fp", "reason": "test"},
        "perf": {"available": True, "version": "perf version 6.8"},
    }

    manifest = capture.build_manifest(
        bundle_dir=tmp_path,
        job_path=tmp_path / "capture-job.yaml",
        job=job,
        profile=profile,
        preflight_result=preflight,
        elapsed_ms=123,
    )

    validate_document(manifest, document_type=CAPTURE_BUNDLE)
    assert manifest["backend"] == "local"
    assert manifest["artifacts"]["proc_maps"] == "proc-4242-maps"
    assert manifest["perf"]["callgraph_mode"] == "fp"
