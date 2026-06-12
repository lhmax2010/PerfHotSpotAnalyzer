from __future__ import annotations

from pathlib import Path

import pytest

from common.device_runner import DeviceRunner, DeviceRunnerError, load_device_profile
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
                "host: 127.0.0.1",
                "user: root",
                "ssh_opts: \"-o ConnectTimeout=5\"",
                "scp_opts: \"-q\"",
                "sdb_serial: emulator-26101",
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


def test_sdb_shell_invokes_serialized_device(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakebin = install_fake_sdb(tmp_path)
    monkeypatch.setenv("PATH", str(fakebin))
    write_device_profile(tmp_path, backend="sdb")
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)

    result = runner.shell("echo sdb-ok", timeout_s=5)

    assert result.returncode == 0
    assert result.stdout == "sdb-ok\n"
    assert "-s emulator-26101 shell echo sdb-ok" in (
        tmp_path / "sdb.log"
    ).read_text(encoding="utf-8")


def test_sdb_push_and_pull_use_sdb_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakebin = install_fake_sdb(tmp_path)
    monkeypatch.setenv("PATH", str(fakebin))
    write_device_profile(tmp_path, backend="sdb")
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("payload\n", encoding="utf-8")

    runner.push(source, "/tmp/source.txt")
    runner.pull("/tmp/source.txt", tmp_path / "pulled.txt")

    log = (tmp_path / "sdb.log").read_text(encoding="utf-8")
    assert f"-s emulator-26101 push {source} /tmp/source.txt" in log
    assert f"-s emulator-26101 pull /tmp/source.txt {tmp_path / 'pulled.txt'}" in log


def test_sdb_failure_reports_remediation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakebin = install_fake_sdb(tmp_path, fails=True)
    monkeypatch.setenv("PATH", str(fakebin))
    write_device_profile(tmp_path, backend="sdb")
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)

    result = runner.shell("echo sdb-ok", timeout_s=5)

    assert result.returncode == 1
    assert "sdb target emulator-26101" in result.stderr
    assert "sdb devices" in result.stderr


def test_ssh_shell_invokes_configured_target_and_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakebin = install_fake_ssh_tools(tmp_path)
    monkeypatch.setenv("PATH", f"{fakebin}:{fakebin.parent}")
    write_device_profile(tmp_path, backend="ssh")
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)

    result = runner.shell("echo remote-ok", timeout_s=5)

    assert result.returncode == 0
    assert result.stdout == "remote-ok\n"
    log = (tmp_path / "ssh.log").read_text(encoding="utf-8")
    assert "-o ConnectTimeout=5 root@127.0.0.1 echo remote-ok" in log


def test_ssh_shell_failure_reports_tizen_remediation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakebin = install_fake_ssh_tools(tmp_path)
    monkeypatch.setenv("PATH", f"{fakebin}:{fakebin.parent}")
    write_device_profile(tmp_path, backend="ssh")
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)

    result = runner.shell("fail-permission", timeout_s=5)

    assert result.returncode == 255
    assert "Permission denied" in result.stderr
    assert "openssh-server" in result.stderr
    assert "authorized_keys" in result.stderr


def test_ssh_push_and_pull_use_scp_with_remote_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakebin = install_fake_ssh_tools(tmp_path)
    monkeypatch.setenv("PATH", f"{fakebin}:{fakebin.parent}")
    write_device_profile(tmp_path, backend="ssh")
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("payload\n", encoding="utf-8")

    runner.push(source, "/tmp/remote/source.txt")
    runner.pull("/tmp/remote/source.txt", tmp_path / "pulled.txt")

    log = (tmp_path / "scp.log").read_text(encoding="utf-8")
    assert f"-q -r {source} root@127.0.0.1:/tmp/remote/source.txt" in log
    assert f"-q -r root@127.0.0.1:/tmp/remote/source.txt {tmp_path / 'pulled.txt'}" in log


def test_ssh_push_failure_raises_clear_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakebin = install_fake_ssh_tools(tmp_path, scp_fails=True)
    monkeypatch.setenv("PATH", f"{fakebin}:{fakebin.parent}")
    write_device_profile(tmp_path, backend="ssh")
    runner = DeviceRunner.from_name("host", repo_root=tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("payload\n", encoding="utf-8")

    with pytest.raises(DeviceRunnerError, match="openssh-server"):
        runner.push(source, "/tmp/remote/source.txt")


def install_fake_ssh_tools(tmp_path: Path, *, scp_fails: bool = False) -> Path:
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    ssh = fakebin / "ssh"
    ssh.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                f"printf '%s\\n' \"$*\" >> {tmp_path / 'ssh.log'}",
                "cmd=\"${@: -1}\"",
                "if [[ \"$cmd\" == fail-* ]]; then echo 'Permission denied (publickey).' >&2; exit 255; fi",
                "if [[ \"$cmd\" == echo* ]]; then eval \"$cmd\"; else echo remote-ok; fi",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    scp = fakebin / "scp"
    scp.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                f"printf '%s\\n' \"$*\" >> {tmp_path / 'scp.log'}",
                "echo 'scp denied' >&2" if scp_fails else "true",
                "exit 1" if scp_fails else "exit 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    scp.chmod(0o755)
    return fakebin


def install_fake_sdb(tmp_path: Path, *, fails: bool = False) -> Path:
    fakebin = tmp_path / "fakebin-sdb"
    fakebin.mkdir()
    sdb = fakebin / "sdb"
    sdb.write_text(
        "\n".join(
            [
                "#!/bin/bash",
                f"printf '%s\\n' \"$*\" >> {tmp_path / 'sdb.log'}",
                "echo 'sdb target offline' >&2" if fails else "true",
                "exit 1" if fails else "if [[ \"$3\" == shell ]]; then cmd=\"${@:4}\"; eval \"$cmd\"; fi",
                "exit 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    sdb.chmod(0o755)
    return fakebin
