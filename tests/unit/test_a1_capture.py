from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

from common.device_runner import CompletedRun, DeviceProfile
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


def test_capture_bundle_schema_accepts_armv7l_arch(tmp_path: Path) -> None:
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
        json.dumps({"cpu_governor": "performance", "affinity": "0", "thermal_state": "unknown"}),
        encoding="utf-8",
    )
    profile = DeviceProfile(
        name="board",
        backend="ssh",
        arch="armv7l",
        path=tmp_path / "board.yaml",
        remote_workdir=Path("/root/perf-skill"),
    )
    job = {
        "target": {"kind": "pid", "pid": 4242, "commit": "abc123"},
        "perf": {"events": ["cycles"], "freq_hz": 499, "duration_s": 2, "repeat": 1, "warmup": 0},
    }

    manifest = capture.build_manifest(
        bundle_dir=tmp_path,
        job_path=tmp_path / "capture-job.yaml",
        job=job,
        profile=profile,
        preflight_result={"callgraph": {"mode": "fp", "reason": "test"}, "perf": {"available": True}},
        elapsed_ms=123,
    )

    validate_document(manifest, document_type=CAPTURE_BUNDLE)
    assert manifest["device"]["arch"] == "armv7l"


def test_remote_capture_uses_device_runner_and_host_folded_generation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    capture = load_capture_module()
    repo = tmp_path / "repo"
    device_dir = repo / ".perf-skill" / "devices"
    device_dir.mkdir(parents=True)
    remote = tmp_path / "remote"
    remote.mkdir()
    (device_dir / "board.yaml").write_text(
        "\n".join(
            [
                "name: board",
                "backend: ssh",
                "host: 127.0.0.1",
                "user: root",
                f"remote_workdir: {remote}",
                "perf_path: /usr/bin/perf",
                "arch: aarch64",
                "target_has_stackcollapse: false",
                "shell_timeout_s: 77",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    job = tmp_path / "capture-job.yaml"
    job.write_text(
        """
        device: board
        target:
          kind: pid
          pid: 4242
        perf:
          events: [cycles]
          freq_hz: 999
          callgraph: auto
          duration_s: 1
          repeat: 1
          warmup: 0
        output:
          bundle_name: tizen-bundle
        """,
        encoding="utf-8",
    )

    pushed_paths: list[str] = []
    script_calls: list[tuple[str, list[str]]] = []
    shell_timeouts: list[int] = []

    class FakeRunner:
        def __init__(self, profile, tracer=None):
            self.profile = profile

        def shell(self, cmd, timeout_s):
            assert "runner.sh" not in cmd
            shell_timeouts.append(timeout_s)
            return CompletedRun(cmd, 0, "", "", 1)

        def shell_script(self, script_text, args, timeout_s):
            script_calls.append((script_text, [str(arg) for arg in args]))
            bundle = self.profile.remote_workdir / "tizen-bundle"
            bundle.mkdir(parents=True, exist_ok=True)
            write_remote_bundle_artifacts(bundle)
            return CompletedRun("bash -s", 0, "", "", 1)

        def push(self, local_path, remote_path):
            pushed_paths.append(str(remote_path))
            assert Path(remote_path).name != "runner.sh"
            Path(remote_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, remote_path)

        def pull(self, remote_path, local_path):
            destination = Path(local_path) / Path(remote_path).name
            shutil.copytree(remote_path, destination, dirs_exist_ok=True)

    monkeypatch.setattr(capture, "DeviceRunner", FakeRunner)

    result = capture.run_capture(
        job_path=job,
        output_dir=tmp_path / "out",
        repo_root=repo,
    )

    assert result.manifest["backend"] == "ssh"
    assert result.manifest["device"]["arch"] == "aarch64"
    assert result.manifest["perf"]["callgraph_mode"] == "dwarf"
    assert (result.bundle_dir / "out.folded").read_text(encoding="utf-8").strip()
    assert pushed_paths == [str(remote / "tizen-bundle" / "capture-job.yaml")]
    assert script_calls
    assert script_calls[0][1][0] == str(remote / "tizen-bundle")
    assert shell_timeouts == [77, 77]
    assert "runner.sh" not in " ".join(script_calls[0][1])
    assert "record_args=" in script_calls[0][0]
    validate_document(result.manifest, document_type=CAPTURE_BUNDLE)


def test_capture_timeout_command_duration_zero_uses_workload_budget(tmp_path: Path) -> None:
    capture = load_capture_module()
    profile = DeviceProfile(
        name="board",
        backend="ssh",
        arch="armv7l",
        path=tmp_path / "board.yaml",
        remote_workdir=Path("/root/perf-skill"),
        command_timeout_s=240,
        perf_script_timeout_s=80,
    )
    job = {
        "target": {"kind": "command", "command": "ffmpeg -i input -f null -"},
        "perf": {"duration_s": 0, "repeat": 1, "warmup": 0},
    }

    assert capture._capture_timeout(job, profile=profile, callgraph_mode="fp") == 320


def test_capture_timeout_job_override_wins(tmp_path: Path) -> None:
    capture = load_capture_module()
    profile = DeviceProfile(
        name="board",
        backend="ssh",
        arch="armv7l",
        path=tmp_path / "board.yaml",
        capture_timeout_s=500,
    )
    job = {
        "target": {"kind": "command", "command": "ffmpeg -i input -f null -"},
        "perf": {"duration_s": 0, "timeout_s": 123},
    }

    assert capture._capture_timeout(job, profile=profile, callgraph_mode="fp") == 123


def test_capture_timeout_expands_dwarf_script_budget_on_armv7l(tmp_path: Path) -> None:
    capture = load_capture_module()
    profile = DeviceProfile(
        name="board",
        backend="ssh",
        arch="armv7l",
        path=tmp_path / "board.yaml",
    )
    job = {
        "target": {"kind": "pid", "pid": 4242},
        "perf": {"duration_s": 10, "repeat": 1, "warmup": 0},
    }

    fp_timeout = capture._capture_timeout(job, profile=profile, callgraph_mode="fp")
    dwarf_timeout = capture._capture_timeout(job, profile=profile, callgraph_mode="dwarf")

    assert fp_timeout == 105
    assert dwarf_timeout == 225


def test_runner_logs_perf_record_and_script_timing() -> None:
    script = (
        ROOT / "skills" / "perf-hotspot-analyzer" / "target-side" / "runner.sh"
    ).read_text(encoding="utf-8")

    assert "run_timed perf-record" in script
    assert "run_redirect_timed perf-script" in script
    assert "elapsed_s=" in script


def write_remote_bundle_artifacts(bundle: Path) -> None:
    (bundle / "perf.data").write_text("fixture\n", encoding="utf-8")
    (bundle / "perf-script.txt").write_text(
        "demo 4242/4242 1.0: 1 hot_symbol (/usr/lib/libdemo.so)\n",
        encoding="utf-8",
    )
    (bundle / "out.folded").write_text("", encoding="utf-8")
    (bundle / "perf-report.txt").write_text("hot_symbol\n", encoding="utf-8")
    (bundle / "kallsyms").write_text("", encoding="utf-8")
    (bundle / "dso-list.txt").write_text("abcd1234 /usr/lib/libdemo.so\n", encoding="utf-8")
    (bundle / "proc-4242-maps").write_text("", encoding="utf-8")
    (bundle / "exec.log").write_text("ok\n", encoding="utf-8")
    (bundle / "run-context.json").write_text(
        json.dumps(
            {
                "cpu_governor": "performance",
                "affinity": "0-1",
                "thermal_state": "unknown",
            }
        ),
        encoding="utf-8",
    )
