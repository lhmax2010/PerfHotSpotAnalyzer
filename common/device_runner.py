"""DeviceRunner abstraction with the A1 local backend implementation."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.simple_yaml import load_yaml


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
    raw: dict[str, Any] = field(default_factory=dict)


class DeviceRunner:
    """Run shell/push/pull against a configured device backend.

    A1 implements only the local backend.  ssh and sdb are intentionally
    reserved for A3 so the x86 fixture chain closes before Tizen device logic.
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

    def push(self, local_path: str | Path, remote_path: str | Path) -> None:
        self._trace("push", "start", local_path=str(local_path), remote_path=str(remote_path))
        if self.profile.backend != "local":
            self._unsupported_backend("push")
            return
        _copy_path(Path(local_path), self._resolve_remote_path(remote_path))
        self._trace("push", "finish", local_path=str(local_path), remote_path=str(remote_path))

    def pull(self, remote_path: str | Path, local_path: str | Path) -> None:
        self._trace("pull", "start", remote_path=str(remote_path), local_path=str(local_path))
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
