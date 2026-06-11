from __future__ import annotations

from pathlib import Path

import pytest

from common.device_runner import DeviceRunner, load_device_profile
from common.simple_yaml import loads_yaml


def write_device_profile(root: Path, *, backend: str = "local") -> Path:
    device_dir = root / ".perf-skill" / "devices"
    device_dir.mkdir(parents=True)
    workdir = root / "remote"
    workdir.mkdir()
    path = device_dir / "host.yaml"
    path.write_text(
        "\n".join(
            [
                "name: host",
                f"backend: {backend}",
                "arch: x86_64",
                f"remote_workdir: {workdir}",
                "perf_path: /usr/bin/perf",
                "needs_sudo: false",
                "target_has_stackcollapse: false",
                "debuginfo_roots:",
                "  - /usr/lib/debug",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_simple_yaml_loads_nested_capture_subset() -> None:
    parsed = loads_yaml(
        """
        device: host
        perf:
          events: [cycles, instructions]
          repeat: 3
          warmup: 1
        output:
          bundle_name: bundle.tar.gz
        """
    )

    assert parsed["device"] == "host"
    assert parsed["perf"]["events"] == ["cycles", "instructions"]
    assert parsed["perf"]["repeat"] == 3


def test_load_device_profile_reads_local_backend(tmp_path: Path) -> None:
    write_device_profile(tmp_path)

    profile = load_device_profile("host", repo_root=tmp_path)

    assert profile.name == "host"
    assert profile.backend == "local"
    assert profile.arch == "x86_64"
    assert profile.perf_path == "/usr/bin/perf"
    assert profile.debuginfo_roots == ["/usr/lib/debug"]


def test_local_shell_runs_in_profile_workdir(tmp_path: Path) -> None:
    write_device_profile(tmp_path)
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)

    result = runner.shell("pwd", timeout_s=5)

    assert result.returncode == 0
    assert result.stdout.strip() == str(tmp_path / "remote")
    assert not result.timed_out


def test_local_shell_reports_timeout(tmp_path: Path) -> None:
    write_device_profile(tmp_path)
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)

    result = runner.shell("sleep 1", timeout_s=0)

    assert result.returncode == 124
    assert result.timed_out


def test_local_push_and_pull_copy_files(tmp_path: Path) -> None:
    write_device_profile(tmp_path)
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("payload\n", encoding="utf-8")

    runner.push(source, "nested/remote.txt")
    pulled = tmp_path / "pulled.txt"
    runner.pull("nested/remote.txt", pulled)

    assert (tmp_path / "remote" / "nested" / "remote.txt").read_text(
        encoding="utf-8"
    ) == "payload\n"
    assert pulled.read_text(encoding="utf-8") == "payload\n"


@pytest.mark.parametrize("backend", ["ssh", "sdb"])
def test_non_local_backends_are_reserved_for_a3(tmp_path: Path, backend: str) -> None:
    write_device_profile(tmp_path, backend=backend)
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)

    with pytest.raises(NotImplementedError, match="reserved for A3"):
        runner.shell("true", timeout_s=1)
