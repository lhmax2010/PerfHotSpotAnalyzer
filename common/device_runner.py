"""DeviceRunner abstraction for local, ssh, and sdb backends."""

from __future__ import annotations

import shutil
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from common.yaml_loader import load_yaml


@dataclass(frozen=True)
class CompletedRun:
    """Result of a command executed through a DeviceRunner backend."""

    args: str
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: int
    timed_out: bool = False


@dataclass(frozen=True)
class DeviceProfile:
    """Device profile loaded from .perf-skill/devices/<name>.yaml."""

    name: str
    backend: str
    arch: str
    path: Path
    host: str | None = None
    user: str | None = None
    ssh_opts: str = ""
    scp_opts: str = ""
    remote_workdir: Path = Path(".")
    perf_path: str = "perf"
    needs_sudo: bool = False
    sysroot: str | None = None
    debuginfo_roots: list[str] = field(default_factory=list)
    target_has_stackcollapse: bool = False
    sdb_serial: str | None = None
    tizen_version: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class DeviceRunnerError(RuntimeError):
    """Raised when a backend operation cannot complete."""


class DeviceRunner:
    """Run shell/push/pull against a configured device backend.

    The local backend is used for x86 fixtures.  The ssh backend is the A3
    Tizen main path, with sdb added as the fallback transport.
    """

    def __init__(self, profile: DeviceProfile, *, tracer: Any | None = None) -> None:
        self.profile = profile
        self.tracer = tracer
        if profile.backend not in {"local", "ssh", "sdb"}:
            raise ValueError(f"unsupported backend: {profile.backend}")

    @classmethod
    def from_name(
        cls,
        name: str,
        *,
        repo_root: str | Path = ".",
        tracer: Any | None = None,
    ) -> "DeviceRunner":
        return cls(load_device_profile(name, repo_root=repo_root), tracer=tracer)

    def shell(self, cmd: str, timeout_s: int) -> CompletedRun:
        self._trace("shell", "start", command=cmd, timeout_s=timeout_s)
        if self.profile.backend == "ssh":
            return self._ssh_shell(cmd, timeout_s)
        if self.profile.backend == "sdb":
            return self._sdb_shell(cmd, timeout_s)
        if self.profile.backend != "local":
            return self._unsupported_backend("shell")
        started = time.monotonic()
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.profile.remote_workdir,
                text=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            completed = CompletedRun(
                args=cmd,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            self._trace(
                "shell",
                "finish",
                command=cmd,
                returncode=completed.returncode,
                elapsed_ms=completed.elapsed_ms,
            )
            return completed
        except subprocess.TimeoutExpired as exc:
            completed = CompletedRun(
                args=cmd,
                returncode=124,
                stdout=_decode_timeout_stream(exc.stdout),
                stderr=_decode_timeout_stream(exc.stderr),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                timed_out=True,
            )
            self._trace(
                "shell",
                "timeout",
                command=cmd,
                returncode=completed.returncode,
                elapsed_ms=completed.elapsed_ms,
            )
            return completed

    def shell_script(
        self,
        script_text: str,
        args: Sequence[str | Path],
        timeout_s: int,
    ) -> CompletedRun:
        argv_args = [str(arg) for arg in args]
        command = "bash -s -- " + " ".join(shlex.quote(arg) for arg in argv_args)
        self._trace("shell_script", "start", command=command, timeout_s=timeout_s)
        if self.profile.backend == "ssh":
            target = self._ssh_target()
            argv = ["ssh", *_split_options(self.profile.ssh_opts), target, command]
            return self._run_backend_command(
                step="shell_script",
                argv=argv,
                timeout_s=timeout_s,
                command_for_result=command,
                remediation=_ssh_remediation(self.profile),
                input_text=script_text,
            )
        if self.profile.backend == "sdb":
            argv = [*_sdb_prefix(self.profile), "shell", command]
            return self._run_backend_command(
                step="shell_script",
                argv=argv,
                timeout_s=timeout_s,
                command_for_result=command,
                remediation=_sdb_remediation(self.profile),
                input_text=script_text,
            )
        if self.profile.backend != "local":
            return self._unsupported_backend("shell_script")
        started = time.monotonic()
        try:
            result = subprocess.run(
                ["bash", "-s", "--", *argv_args],
                input=script_text,
                cwd=self.profile.remote_workdir,
                text=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            completed = CompletedRun(
                args=command,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            self._trace(
                "shell_script",
                "finish",
                returncode=completed.returncode,
                elapsed_ms=completed.elapsed_ms,
            )
            return completed
        except subprocess.TimeoutExpired as exc:
            completed = CompletedRun(
                args=command,
                returncode=124,
                stdout=_decode_timeout_stream(exc.stdout),
                stderr=_decode_timeout_stream(exc.stderr),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                timed_out=True,
            )
            self._trace(
                "shell_script",
                "timeout",
                returncode=completed.returncode,
                elapsed_ms=completed.elapsed_ms,
            )
            return completed

    def push(self, local_path: str | Path, remote_path: str | Path) -> None:
        self._trace("push", "start", local_path=str(local_path), remote_path=str(remote_path))
        if self.profile.backend == "ssh":
            self._ssh_copy("push", Path(local_path), remote_path)
            return
        if self.profile.backend == "sdb":
            self._sdb_copy("push", Path(local_path), remote_path)
            return
        if self.profile.backend != "local":
            self._unsupported_backend("push")
            return
        _copy_path(Path(local_path), self._resolve_remote_path(remote_path))
        self._trace("push", "finish", local_path=str(local_path), remote_path=str(remote_path))

    def pull(self, remote_path: str | Path, local_path: str | Path) -> None:
        self._trace("pull", "start", remote_path=str(remote_path), local_path=str(local_path))
        if self.profile.backend == "ssh":
            self._ssh_copy("pull", Path(local_path), remote_path)
            return
        if self.profile.backend == "sdb":
            self._sdb_copy("pull", Path(local_path), remote_path)
            return
        if self.profile.backend != "local":
            self._unsupported_backend("pull")
            return
        _copy_path(self._resolve_remote_path(remote_path), Path(local_path))
        self._trace("pull", "finish", remote_path=str(remote_path), local_path=str(local_path))

    def _resolve_remote_path(self, value: str | Path) -> Path:
        path = Path(value).expanduser()
        if path.is_absolute():
            return path
        return self.profile.remote_workdir / path

    def _unsupported_backend(self, operation: str) -> CompletedRun:
        message = (
            f"{self.profile.backend} backend {operation} is reserved for A3; "
            "A1 implements only backend=local"
        )
        self._trace(operation, "unsupported_backend", backend=self.profile.backend)
        raise NotImplementedError(message)

    def _ssh_shell(self, cmd: str, timeout_s: int) -> CompletedRun:
        target = self._ssh_target()
        argv = ["ssh", *_split_options(self.profile.ssh_opts), target, cmd]
        return self._run_backend_command(
            step="shell",
            argv=argv,
            timeout_s=timeout_s,
            command_for_result=cmd,
            remediation=_ssh_remediation(self.profile),
        )

    def _ssh_copy(
        self,
        direction: str,
        local_path: Path,
        remote_path: str | Path,
    ) -> None:
        target_path = self._remote_spec(remote_path)
        recursive = ["-r"]
        if direction == "push":
            argv = [
                "scp",
                *_split_options(self.profile.scp_opts),
                *recursive,
                str(local_path),
                target_path,
            ]
        else:
            argv = [
                "scp",
                *_split_options(self.profile.scp_opts),
                *recursive,
                target_path,
                str(local_path),
            ]
        completed = self._run_backend_command(
            step=direction,
            argv=argv,
            timeout_s=60,
            command_for_result=" ".join(argv),
            remediation=_ssh_remediation(self.profile),
        )
        if completed.returncode != 0:
            raise DeviceRunnerError(completed.stderr)

    def _run_backend_command(
        self,
        *,
        step: str,
        argv: list[str],
        timeout_s: int,
        command_for_result: str,
        remediation: str,
        input_text: str | None = None,
    ) -> CompletedRun:
        self._trace(step, "exec", argv=argv, timeout_s=timeout_s)
        started = time.monotonic()
        try:
            result = subprocess.run(
                argv,
                input=input_text,
                text=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            stderr = result.stderr
            if result.returncode != 0:
                stderr = _with_remediation(stderr, remediation)
            completed = CompletedRun(
                args=command_for_result,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=stderr,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            self._trace(
                step,
                "finish",
                returncode=completed.returncode,
                elapsed_ms=completed.elapsed_ms,
            )
            return completed
        except subprocess.TimeoutExpired as exc:
            completed = CompletedRun(
                args=command_for_result,
                returncode=124,
                stdout=_decode_timeout_stream(exc.stdout),
                stderr=_with_remediation(
                    _decode_timeout_stream(exc.stderr) or f"{step} timed out",
                    remediation,
                ),
                elapsed_ms=int((time.monotonic() - started) * 1000),
                timed_out=True,
            )
            self._trace(
                step,
                "timeout",
                returncode=completed.returncode,
                elapsed_ms=completed.elapsed_ms,
            )
            return completed

    def _ssh_target(self) -> str:
        if not self.profile.host:
            raise DeviceRunnerError("ssh backend requires device profile field 'host'")
        if self.profile.user:
            return f"{self.profile.user}@{self.profile.host}"
        return self.profile.host

    def _remote_spec(self, value: str | Path) -> str:
        return f"{self._ssh_target()}:{value}"

    def _sdb_shell(self, cmd: str, timeout_s: int) -> CompletedRun:
        argv = [*_sdb_prefix(self.profile), "shell", cmd]
        return self._run_backend_command(
            step="shell",
            argv=argv,
            timeout_s=timeout_s,
            command_for_result=cmd,
            remediation=_sdb_remediation(self.profile),
        )

    def _sdb_copy(
        self,
        direction: str,
        local_path: Path,
        remote_path: str | Path,
    ) -> None:
        if direction == "push":
            argv = [*_sdb_prefix(self.profile), "push", str(local_path), str(remote_path)]
        else:
            argv = [*_sdb_prefix(self.profile), "pull", str(remote_path), str(local_path)]
        completed = self._run_backend_command(
            step=direction,
            argv=argv,
            timeout_s=60,
            command_for_result=" ".join(argv),
            remediation=_sdb_remediation(self.profile),
        )
        if completed.returncode != 0:
            raise DeviceRunnerError(completed.stderr)

    def _trace(self, step: str, event: str, **fields: Any) -> None:
        if self.tracer is not None:
            self.tracer.info(f"device_runner.{step}", event, **fields)


def load_device_profile(name: str, *, repo_root: str | Path = ".") -> DeviceProfile:
    repo = Path(repo_root)
    profile_path = repo / ".perf-skill" / "devices" / f"{name}.yaml"
    if not profile_path.exists():
        raise FileNotFoundError(f"device profile not found: {profile_path}")
    raw = load_yaml(profile_path)
    backend = str(raw.get("backend", "")).strip()
    if backend not in {"local", "ssh", "sdb"}:
        raise ValueError(f"{profile_path}: backend must be one of local, ssh, sdb")
    profile_name = str(raw.get("name") or name)
    remote_workdir = Path(str(raw.get("remote_workdir") or ".")).expanduser()
    if backend == "local" and not remote_workdir.is_absolute():
        remote_workdir = (profile_path.parent / remote_workdir).resolve()
    return DeviceProfile(
        name=profile_name,
        backend=backend,
        arch=str(raw.get("arch") or "x86_64"),
        path=profile_path,
        host=_optional_str(raw.get("host")),
        user=_optional_str(raw.get("user")),
        ssh_opts=str(raw.get("ssh_opts") or ""),
        scp_opts=str(raw.get("scp_opts") or ""),
        remote_workdir=remote_workdir,
        perf_path=str(raw.get("perf_path") or "perf"),
        needs_sudo=bool(raw.get("needs_sudo", False)),
        sysroot=_optional_str(raw.get("sysroot")),
        debuginfo_roots=[str(item) for item in raw.get("debuginfo_roots", [])],
        target_has_stackcollapse=bool(raw.get("target_has_stackcollapse", False)),
        sdb_serial=_optional_str(raw.get("sdb_serial") or raw.get("serial")),
        tizen_version=_optional_str(raw.get("tizen_version")),
        raw=raw,
    )


def _copy_path(source: Path, destination: Path) -> None:
    source = source.expanduser()
    destination = destination.expanduser()
    if source.is_dir():
        if destination.exists() and destination.is_file():
            raise NotADirectoryError(str(destination))
        shutil.copytree(source, destination, dirs_exist_ok=True)
        return
    if destination.exists() and destination.is_dir():
        destination = destination / source.name
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _decode_timeout_stream(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _split_options(options: str) -> list[str]:
    values = []
    for option in shlex.split(options):
        values.append(str(Path(option).expanduser()) if option.startswith("~") else option)
    return values


def _with_remediation(stderr: str, remediation: str) -> str:
    text = stderr.strip()
    if text:
        text += "\n"
    return text + remediation


def _ssh_remediation(profile: DeviceProfile) -> str:
    target = profile.host or "<missing-host>"
    return (
        f"Remediation for ssh target {target}: verify network reachability, ssh key "
        "authorization, user/host in the device profile, and Tizen image prerequisites. "
        "For Tizen, use a root image or install/enable openssh-server, run "
        "`systemctl enable sshd && systemctl start sshd`, and add the host public key "
        "to ~/.ssh/authorized_keys. The scripts never run sudo or change target policy."
    )


def _sdb_prefix(profile: DeviceProfile) -> list[str]:
    if profile.sdb_serial:
        return ["sdb", "-s", profile.sdb_serial]
    return ["sdb"]


def _sdb_remediation(profile: DeviceProfile) -> str:
    serial = profile.sdb_serial or "<default-device>"
    return (
        f"Remediation for sdb target {serial}: verify Tizen Studio sdb is installed, "
        "`sdb devices` shows the target as connected, the target has developer/root "
        "access enabled, and the serial in the device profile is correct. The scripts "
        "never run sudo or change target policy."
    )
