"""Preflight checks for local perf capture."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from common.tracing import TraceLogger, start_trace


CAP_PERFMON = 38
DEFAULT_TIMEOUT_S = 5


def run_preflight(
    *,
    perf_path: str = "perf",
    requested_callgraph: str = "auto",
    paranoid_path: str | Path = "/proc/sys/kernel/perf_event_paranoid",
    status_path: str | Path = "/proc/self/status",
    arch: str | None = None,
    tracer: TraceLogger | None = None,
) -> dict[str, Any]:
    perf = detect_perf(perf_path)
    paranoid = read_perf_event_paranoid(paranoid_path)
    cap_perfmon = detect_cap_perfmon(status_path=status_path)
    euid = _geteuid()
    permissions = assess_permissions(paranoid, cap_perfmon, euid=euid)
    callgraph = choose_callgraph_mode(
        requested=requested_callgraph,
        perf_available=perf["available"],
        arch=arch or platform.machine(),
    )
    result = {
        "schema_version": "preflight/v1",
        "timestamp": datetime.now(UTC).isoformat(),
        "perf": perf,
        "kernel": {
            "perf_event_paranoid": paranoid,
            "cap_perfmon": cap_perfmon,
            "euid": euid,
            "permissions_ok": permissions["ok"],
            "permission_reason": permissions["reason"],
            "remediation": permissions["remediation"],
        },
        "callgraph": callgraph,
    }
    if tracer is not None:
        tracer.info(
            "preflight",
            "callgraph_chosen",
            mode=callgraph["mode"],
            reason=callgraph["reason"],
        )
        tracer.info(
            "preflight",
            "permission_checked",
            permissions_ok=permissions["ok"],
            perf_event_paranoid=paranoid,
            cap_perfmon=cap_perfmon,
        )
    return result


def detect_perf(perf_path: str = "perf") -> dict[str, Any]:
    executable = shutil.which(perf_path) or (
        perf_path if Path(perf_path).exists() else None
    )
    if executable is None:
        return {
            "path": perf_path,
            "available": False,
            "version": None,
            "error": f"{perf_path} not found on PATH",
        }
    try:
        result = subprocess.run(
            [executable, "--version"],
            text=True,
            capture_output=True,
            timeout=DEFAULT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "path": executable,
            "available": False,
            "version": None,
            "error": str(exc),
        }
    output = (result.stdout or result.stderr).strip()
    return {
        "path": executable,
        "available": result.returncode == 0,
        "version": output or None,
        "error": None if result.returncode == 0 else output,
    }


def read_perf_event_paranoid(path: str | Path = "/proc/sys/kernel/perf_event_paranoid") -> int | None:
    try:
        return int(Path(path).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def detect_cap_perfmon(
    *,
    status_text: str | None = None,
    status_path: str | Path = "/proc/self/status",
) -> bool:
    if status_text is None:
        try:
            status_text = Path(status_path).read_text(encoding="utf-8")
        except OSError:
            return False
    for line in status_text.splitlines():
        if line.startswith("CapEff:"):
            _, raw_value = line.split(":", 1)
            return _has_capability(raw_value.strip(), CAP_PERFMON)
    return False


def assess_permissions(
    paranoid: int | None,
    cap_perfmon: bool,
    *,
    euid: int | None = None,
) -> dict[str, Any]:
    effective_uid = _geteuid() if euid is None else euid
    if effective_uid == 0:
        return {"ok": True, "reason": "running as root", "remediation": []}
    if cap_perfmon:
        return {"ok": True, "reason": "CAP_PERFMON present", "remediation": []}
    if paranoid is not None and paranoid <= 1:
        return {
            "ok": True,
            "reason": f"perf_event_paranoid={paranoid} allows user profiling",
            "remediation": [],
        }
    return {
        "ok": False,
        "reason": (
            "perf_event_paranoid is restrictive and CAP_PERFMON is not present"
            if paranoid is not None
            else "cannot read perf_event_paranoid and CAP_PERFMON is not present"
        ),
        "remediation": [
            "Ask an administrator to lower /proc/sys/kernel/perf_event_paranoid for this host.",
            "Ask an administrator to grant CAP_PERFMON to the perf executable.",
            "Run capture on a host or target profile where perf sampling is permitted.",
        ],
    }


def choose_callgraph_mode(
    *,
    requested: str,
    perf_available: bool,
    arch: str,
) -> dict[str, str]:
    if requested in {"fp", "dwarf", "none"}:
        return {"mode": requested, "reason": f"capture job requested {requested}"}
    if requested != "auto":
        raise ValueError("callgraph must be one of auto, fp, dwarf, none")
    if not perf_available:
        return {"mode": "none", "reason": "perf is unavailable"}
    if _frame_pointer_preferred(arch):
        return {
            "mode": "fp",
            "reason": f"{arch} local capture prefers frame-pointer callgraphs first",
        }
    return {
        "mode": "dwarf",
        "reason": f"{arch} does not default to fp in A1; falling back to DWARF",
    }


def write_preflight(path: str | Path, data: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check perf capture prerequisites.")
    parser.add_argument("--perf-path", default="perf")
    parser.add_argument(
        "--callgraph",
        default="auto",
        choices=["auto", "fp", "dwarf", "none"],
        help="Requested callgraph mode; auto probes fp then dwarf then none.",
    )
    parser.add_argument("--output", required=True, help="Path for preflight.json.")
    parser.add_argument("--output-dir", default="out", help="Trace output directory.")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    tracer = start_trace(
        skill="perf-hotspot-analyzer",
        output_dir=args.output_dir,
        verbose=args.verbose,
    )
    try:
        result = run_preflight(
            perf_path=args.perf_path,
            requested_callgraph=args.callgraph,
            tracer=tracer,
        )
        write_preflight(args.output, result)
    finally:
        tracer.close()
    return 0


def _has_capability(raw_hex: str, capability: int) -> bool:
    try:
        mask = int(raw_hex, 16)
    except ValueError:
        return False
    return bool(mask & (1 << capability))


def _frame_pointer_preferred(arch: str) -> bool:
    return arch.lower() in {"x86_64", "amd64", "i386", "i686"}


def _geteuid() -> int | None:
    return os.geteuid() if hasattr(os, "geteuid") else None


if __name__ == "__main__":
    raise SystemExit(main())
