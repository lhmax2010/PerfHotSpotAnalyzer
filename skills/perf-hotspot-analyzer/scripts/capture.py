"""Capture local perf data into a self-contained Capture Bundle."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from common.device_runner import DeviceProfile, DeviceRunner, load_device_profile
from common.schema_validate import CAPTURE_BUNDLE, validate_document
from common.simple_yaml import load_yaml
from common.tracing import TraceLogger, start_trace


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import preflight  # noqa: E402


REQUIRED_ARTIFACTS = {
    "perf_data": "perf.data",
    "perf_script": "perf-script.txt",
    "folded": "out.folded",
    "perf_report": "perf-report.txt",
    "kallsyms": "kallsyms",
    "dso_list": "dso-list.txt",
    "run_context": "run-context.json",
    "exec_log": "exec.log",
}


@dataclass(frozen=True)
class CaptureResult:
    bundle_dir: Path
    manifest: dict[str, Any]
    preflight: dict[str, Any]


def load_capture_job(path: str | Path) -> dict[str, Any]:
    job = load_yaml(path)
    if "device" not in job:
        raise ValueError("capture job requires device")
    if not isinstance(job.get("target"), dict):
        raise ValueError("capture job requires target mapping")
    if not isinstance(job.get("perf"), dict):
        raise ValueError("capture job requires perf mapping")
    return job


def run_capture(
    *,
    job_path: str | Path,
    output_dir: str | Path,
    repo_root: str | Path = ".",
    tracer: TraceLogger | None = None,
    keep_remote: bool = False,
) -> CaptureResult:
    job_path = Path(job_path)
    repo_root = Path(repo_root)
    job = load_capture_job(job_path)
    profile = load_device_profile(str(job["device"]), repo_root=repo_root)

    requested_callgraph = str(job.get("perf", {}).get("callgraph", "auto"))
    preflight_result = run_capture_preflight(
        profile=profile,
        requested_callgraph=requested_callgraph,
        tracer=tracer,
    )
    callgraph_mode = preflight_result["callgraph"]["mode"]
    bundle_stem = _bundle_stem(job)
    output_root = Path(output_dir)
    local_bundle_dir = output_root / bundle_stem
    remote_bundle_dir = profile.remote_workdir / bundle_stem
    local_bundle_dir.mkdir(parents=True, exist_ok=True)

    runner = DeviceRunner(profile, tracer=tracer)
    runner.shell(f"mkdir -p {shlex.quote(str(remote_bundle_dir))}", timeout_s=10)
    runner.push(job_path, remote_bundle_dir / "capture-job.yaml")
    runner.push(_runner_script_path(), remote_bundle_dir / "runner.sh")

    command = build_runner_command(
        remote_bundle_dir=remote_bundle_dir,
        profile=profile,
        job=job,
        callgraph_mode=callgraph_mode,
    )
    started = time.monotonic()
    run = runner.shell(command, timeout_s=_capture_timeout(job))
    if run.returncode != 0:
        raise RuntimeError(f"capture runner failed with {run.returncode}: {run.stderr}")
    if profile.backend == "local":
        runner.pull(remote_bundle_dir, local_bundle_dir)
    else:
        runner.pull(remote_bundle_dir, output_root)

    if not keep_remote:
        runner.shell(f"rm -rf {shlex.quote(str(remote_bundle_dir))}", timeout_s=10)

    ensure_folded_from_perf_script(local_bundle_dir)
    manifest = build_manifest(
        bundle_dir=local_bundle_dir,
        job_path=job_path,
        job=job,
        profile=profile,
        preflight_result=preflight_result,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
    manifest_path = local_bundle_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validate_document(manifest, document_type=CAPTURE_BUNDLE)
    if tracer is not None:
        tracer.info(
            "capture",
            "bundle_ready",
            bundle_dir=str(local_bundle_dir),
            callgraph_mode=callgraph_mode,
        )
    return CaptureResult(
        bundle_dir=local_bundle_dir,
        manifest=manifest,
        preflight=preflight_result,
    )


def build_runner_command(
    *,
    remote_bundle_dir: Path,
    profile: DeviceProfile,
    job: dict[str, Any],
    callgraph_mode: str,
) -> str:
    target = job["target"]
    perf = job["perf"]
    events = ",".join(str(event) for event in perf.get("events", ["cycles"]))
    args = [
        "bash",
        str(remote_bundle_dir / "runner.sh"),
        str(remote_bundle_dir),
        profile.perf_path,
        str(target.get("kind")),
        _target_value(target),
        events,
        str(perf.get("freq_hz", 999)),
        callgraph_mode,
        str(perf.get("duration_s", 30)),
        str(perf.get("repeat", 1)),
        str(perf.get("warmup", 0)),
        "true" if profile.target_has_stackcollapse else "false",
    ]
    return " ".join(shlex.quote(arg) for arg in args)


def run_capture_preflight(
    *,
    profile: DeviceProfile,
    requested_callgraph: str,
    tracer: TraceLogger | None = None,
) -> dict[str, Any]:
    if profile.backend == "local":
        return preflight.run_preflight(
            perf_path=profile.perf_path,
            requested_callgraph=requested_callgraph,
            arch=profile.arch,
            tracer=tracer,
        )
    callgraph = preflight.choose_callgraph_mode(
        requested=requested_callgraph,
        perf_available=True,
        arch=profile.arch,
    )
    result = {
        "schema_version": "preflight/v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "perf": {
            "path": profile.perf_path,
            "available": True,
            "version": "target-side",
            "error": None,
        },
        "kernel": {
            "perf_event_paranoid": None,
            "cap_perfmon": False,
            "euid": None,
            "permissions_ok": None,
            "permission_reason": "checked on target by runner.sh",
            "remediation": [
                "If capture fails, verify target perf permissions, CAP_PERFMON, and perf_event_paranoid.",
            ],
        },
        "callgraph": callgraph,
    }
    if tracer is not None:
        tracer.info(
            "preflight",
            "remote_callgraph_chosen",
            backend=profile.backend,
            mode=callgraph["mode"],
            reason=callgraph["reason"],
        )
    return result


def build_manifest(
    *,
    bundle_dir: str | Path,
    job_path: str | Path,
    job: dict[str, Any],
    profile: DeviceProfile,
    preflight_result: dict[str, Any],
    elapsed_ms: int,
) -> dict[str, Any]:
    bundle = Path(bundle_dir)
    run_context = _load_json(bundle / "run-context.json", default={})
    dso_entries = parse_dso_list(bundle / "dso-list.txt")
    proc_maps = _find_proc_maps(bundle)
    artifacts = dict(REQUIRED_ARTIFACTS)
    artifacts["proc_maps"] = proc_maps.name if proc_maps is not None else "proc-unknown-maps"
    manifest = {
        "schema_version": "capture-bundle/v1",
        "backend": profile.backend,
        "device": {
            "name": profile.name,
            "host": profile.host or "host",
            "arch": profile.arch,
            "tizen_version": profile.tizen_version or "",
            "sysroot": profile.sysroot or "",
            "debuginfo_roots": list(profile.debuginfo_roots),
            "target_has_stackcollapse": profile.target_has_stackcollapse,
        },
        "capture_job": "capture-job.yaml",
        "target": _manifest_target(job.get("target", {})),
        "perf": {
            "events": [str(event) for event in job.get("perf", {}).get("events", ["cycles"])],
            "freq_hz": int(job.get("perf", {}).get("freq_hz", 999)),
            "callgraph_mode": preflight_result["callgraph"]["mode"],
            "duration_s": float(job.get("perf", {}).get("duration_s", 30)),
            "repeat": int(job.get("perf", {}).get("repeat", 1)),
            "warmup": int(job.get("perf", {}).get("warmup", 0)),
        },
        "run_context": {
            "cpu_governor": str(run_context.get("cpu_governor", "unknown")),
            "affinity": str(run_context.get("affinity", "unknown")),
            "thermal_state": str(run_context.get("thermal_state", "unknown")),
            "elapsed_ms": elapsed_ms,
            "repeat_count": int(job.get("perf", {}).get("repeat", 1)),
            "warmup_count": int(job.get("perf", {}).get("warmup", 0)),
            "preflight": preflight_result,
        },
        "artifacts": artifacts,
        "dsos": dso_entries,
        "provenance": {
            "generated_by": "perf-hotspot-analyzer/capture",
            "captured_by": "perf-hotspot-analyzer/capture",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_job": str(Path(job_path)),
        },
    }
    return manifest


def ensure_folded_from_perf_script(bundle_dir: str | Path) -> None:
    bundle = Path(bundle_dir)
    folded = bundle / "out.folded"
    if folded.exists() and folded.read_text(encoding="utf-8", errors="replace").strip():
        return
    perf_script = bundle / "perf-script.txt"
    folded.write_text(
        "\n".join(_collapse_perf_script(perf_script.read_text(encoding="utf-8", errors="replace")))
        + "\n",
        encoding="utf-8",
    )


def parse_dso_list(path: str | Path) -> list[dict[str, Any]]:
    dso_path = Path(path)
    if not dso_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in dso_path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        parts = text.split()
        build_id = parts[0] if parts else ""
        dso = parts[-1] if parts else text
        entries.append(
            {
                "path": dso,
                "build_id": build_id if build_id != dso else "",
                "load_addr": "",
                "has_debuginfo_on_device": False,
            }
        )
    return entries


def write_run_report(
    *,
    output_dir: str | Path,
    trace_id: str,
    started_at: str,
    total_ms: int,
    result: CaptureResult,
    exit_status: str = "success",
    errors: Sequence[str] = (),
) -> None:
    report = {
        "schema_version": "run-report/v1",
        "trace_id": trace_id,
        "skill": "perf-hotspot-analyzer",
        "started_at": started_at,
        "total_ms": total_ms,
        "by_step": {"preflight": 0, "capture": total_ms},
        "input": {
            "callgraph_mode": result.manifest["perf"]["callgraph_mode"],
            "bundle_dir": str(result.bundle_dir),
            "source_formats": ["perf-script"],
        },
        "findings": {"total": 0, "by_kind": {}},
        "anchors": {"resolved": 0, "confidence_distribution": {}},
        "gate_decisions": [],
        "patches": {"diff-ready": 0, "needs-review": 0, "advisory-only": 0},
        "degradations": [],
        "exit_status": exit_status,
        "errors": list(errors),
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "run-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture perf data into a bundle.")
    parser.add_argument("--job", required=True, help="capture-job.yaml path")
    parser.add_argument("--repo-root", default=".", help="Repository root containing .perf-skill")
    parser.add_argument("--output-dir", required=True, help="Directory for bundle output")
    parser.add_argument("--keep-remote", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    tracer = start_trace(
        skill="perf-hotspot-analyzer",
        output_dir=args.output_dir,
        verbose=args.verbose,
    )
    errors: list[str] = []
    try:
        result = run_capture(
            job_path=args.job,
            output_dir=args.output_dir,
            repo_root=args.repo_root,
            tracer=tracer,
            keep_remote=args.keep_remote,
        )
        write_run_report(
            output_dir=args.output_dir,
            trace_id=tracer.trace_id,
            started_at=started_at,
            total_ms=int((time.monotonic() - started) * 1000),
            result=result,
        )
    except Exception as exc:
        errors.append(str(exc))
        tracer.error("capture", "failed", error=str(exc))
        raise
    finally:
        tracer.close()
    return 0


def _bundle_stem(job: dict[str, Any]) -> str:
    output = job.get("output", {})
    bundle_name = str(output.get("bundle_name") or f"bundle-{int(time.time())}")
    for suffix in (".tar.gz", ".tgz", ".zip"):
        if bundle_name.endswith(suffix):
            return bundle_name[: -len(suffix)]
    return bundle_name


def _capture_timeout(job: dict[str, Any]) -> int:
    perf = job.get("perf", {})
    duration = float(perf.get("duration_s", 30))
    repeat = int(perf.get("repeat", 1))
    warmup = int(perf.get("warmup", 0))
    return int(max(30, (duration + 5) * max(1, repeat + warmup) + 30))


def _target_value(target: dict[str, Any]) -> str:
    kind = target.get("kind")
    if kind == "pid":
        return str(target.get("pid"))
    if kind == "command":
        return str(target.get("command") or target.get("cmdline"))
    if kind == "service":
        return str(target.get("service"))
    raise ValueError("target.kind must be pid, command, or service")


def _manifest_target(target: dict[str, Any]) -> dict[str, Any]:
    kind = str(target.get("kind"))
    return {
        "kind": kind,
        "pid": int(target["pid"]) if kind == "pid" and target.get("pid") else None,
        "cmdline": str(target.get("command") or target.get("cmdline") or "")
        if kind == "command"
        else None,
        "service": str(target.get("service") or "") if kind == "service" else None,
        "commit": target.get("commit"),
    }


def _load_json(path: Path, *, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _find_proc_maps(bundle: Path) -> Path | None:
    matches = sorted(bundle.glob("proc-*-maps"))
    return matches[0] if matches else None


def _collapse_perf_script(text: str) -> list[str]:
    counts: dict[str, int] = {}
    current: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if current:
                stack = ";".join(reversed(current))
                counts[stack] = counts.get(stack, 0) + 1
                current = []
            continue
        if line.startswith("#"):
            continue
        symbol = _extract_symbol(line)
        if symbol:
            current.append(symbol)
    if current:
        stack = ";".join(reversed(current))
        counts[stack] = counts.get(stack, 0) + 1
    return [f"{stack} {count}" for stack, count in sorted(counts.items())]


def _extract_symbol(line: str) -> str | None:
    if " " not in line and "\t" not in line:
        return line
    parts = line.split()
    if len(parts) >= 2 and parts[0].startswith("0x"):
        return parts[1]
    if len(parts) >= 2 and parts[0].endswith(":"):
        return parts[1]
    if len(parts) >= 5:
        return parts[-2]
    return None


def _runner_script_path() -> Path:
    return SCRIPT_DIR.parent / "target-side" / "runner.sh"


if __name__ == "__main__":
    raise SystemExit(main())
