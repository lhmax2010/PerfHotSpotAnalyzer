"""CLI entrypoint for the perf-hotspot-analyzer skill."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from common import schema_validate
from common.cli_base import (
    EXIT_FATAL,
    EXIT_INPUT_UNREADABLE,
    EXIT_SUCCESS,
    EXIT_TIMEOUT,
)
from common.schema_validate import CAPTURE_BUNDLE, PERFORMANCE_FINDINGS, SchemaValidationError
from common.tracing import start_trace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "skills" / "perf-hotspot-analyzer" / "scripts"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    output_dir = Path(getattr(args, "output_dir", "out"))
    tracer = start_trace(
        skill="perf-hotspot-analyzer",
        output_dir=output_dir,
        verbose=getattr(args, "verbose", False),
    )
    errors: list[str] = []
    exit_code = EXIT_SUCCESS
    wrote_run_report = False
    try:
        if args.command == "validate":
            schema_validate.validate_file(
                args.input,
                document_type=args.document_type,
                schema_path=args.schema,
                skill="perf-hotspot-analyzer",
            )
        elif args.command == "capture":
            capture = _load_script("capture")
            result = capture.run_capture(
                job_path=args.job,
                output_dir=args.output_dir,
                repo_root=args.repo_root,
                tracer=tracer,
                keep_remote=args.keep_remote,
            )
            capture.write_run_report(
                output_dir=args.output_dir,
                trace_id=tracer.trace_id,
                started_at=started_at,
                total_ms=int((time.monotonic() - started) * 1000),
                result=result,
            )
            wrote_run_report = True
        elif args.command == "analyze":
            postprocess = _load_script("postprocess")
            analysis = postprocess.postprocess_bundle(
                bundle_dir=args.bundle_dir,
                output=args.output,
                repo_root=args.repo_root,
                ownership_path=args.ownership,
                top_n=args.top_n,
                tracer=tracer,
            )
            postprocess.write_run_report(
                output_dir=args.output_dir,
                trace_id=tracer.trace_id,
                started_at=started_at,
                total_ms=int((time.monotonic() - started) * 1000),
                analysis=analysis,
            )
            wrote_run_report = True
        elif args.command == "report":
            build_report = _load_script("build_report")
            build_report.build_report(
                analysis_path=args.analysis,
                output_dir=args.output_dir,
                repo_root=args.repo_root,
                tracer=tracer,
            )
            wrote_run_report = True
        elif args.command == "binary-size":
            binary_size = _load_script("binary_size")
            document = binary_size.build_binary_size_document(
                elf_path=args.elf,
                baseline_path=args.baseline,
                repo_root=args.repo_root,
                ownership_path=args.ownership,
                user_budget_bytes=args.user_budget_bytes,
                readelf=args.readelf,
            )
            binary_size.write_binary_size_outputs(
                document=document,
                output_dir=args.output_dir,
                trace_id=tracer.trace_id,
                started_at=started_at,
                total_ms=int((time.monotonic() - started) * 1000),
            )
            tracer.info(
                "binary-size",
                "validated",
                findings=len(document.get("findings", [])),
                baseline=bool(args.baseline),
            )
            wrote_run_report = True
        else:
            parser.error(f"unsupported command {args.command}")
    except TimeoutError as exc:
        exit_code = EXIT_TIMEOUT
        errors.append(str(exc))
        tracer.error(args.command, "timeout", error=str(exc))
    except FileNotFoundError as exc:
        exit_code = EXIT_INPUT_UNREADABLE
        errors.append(str(exc))
        tracer.error(args.command, "input_unreadable", error=str(exc))
    except OSError as exc:
        exit_code = EXIT_INPUT_UNREADABLE
        errors.append(str(exc))
        tracer.error(args.command, "io_error", error=str(exc))
    except (json.JSONDecodeError, SchemaValidationError, ValueError, RuntimeError) as exc:
        exit_code = EXIT_FATAL
        errors.append(str(exc))
        tracer.error(args.command, "failed", error=str(exc))
    finally:
        if not wrote_run_report:
            _write_cli_run_report(
                output_dir=output_dir,
                trace_id=tracer.trace_id,
                started_at=started_at,
                total_ms=int((time.monotonic() - started) * 1000),
                command=args.command,
                exit_status="success" if exit_code == EXIT_SUCCESS else "failed",
                errors=errors,
            )
        tracer.close()
    for error in errors:
        print(error, file=sys.stderr)
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="perf-hotspot-analyzer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate analyzer JSON contracts.")
    validate.add_argument("--input", required=True)
    validate.add_argument(
        "--document-type",
        choices=[PERFORMANCE_FINDINGS, CAPTURE_BUNDLE],
        default=PERFORMANCE_FINDINGS,
    )
    validate.add_argument("--schema")
    validate.add_argument("--output-dir", default="out")
    validate.add_argument("--verbose", action="store_true")

    capture = subparsers.add_parser("capture", help="Capture a local perf bundle.")
    capture.add_argument("--job", required=True)
    capture.add_argument("--repo-root", default=".")
    capture.add_argument("--output-dir", required=True)
    capture.add_argument("--keep-remote", action="store_true")
    capture.add_argument("--verbose", action="store_true")

    analyze = subparsers.add_parser("analyze", help="Analyze a Capture Bundle.")
    analyze.add_argument("--bundle-dir", required=True)
    analyze.add_argument("--repo-root", default=".")
    analyze.add_argument("--ownership")
    analyze.add_argument("--output", required=True)
    analyze.add_argument("--output-dir", default="out")
    analyze.add_argument("--top-n", type=int, default=10)
    analyze.add_argument("--verbose", action="store_true")

    report = subparsers.add_parser("report", help="Build performance-findings.json.")
    report.add_argument("--analysis", required=True)
    report.add_argument("--repo-root", default=".")
    report.add_argument("--output-dir", required=True)
    report.add_argument("--verbose", action="store_true")

    binary_size = subparsers.add_parser("binary-size", help="Analyze ELF section sizes.")
    binary_size.add_argument("--elf", required=True, help="Current ELF file.")
    binary_size.add_argument("--baseline", help="Baseline ELF for regression comparison.")
    binary_size.add_argument("--repo-root", default=".")
    binary_size.add_argument("--ownership", help="Optional ownership.yaml path.")
    binary_size.add_argument("--user-budget-bytes", type=int)
    binary_size.add_argument("--readelf", default="readelf")
    binary_size.add_argument("--output-dir", required=True)
    binary_size.add_argument("--verbose", action="store_true")
    return parser


def _load_script(name: str) -> Any:
    path = SCRIPT_ROOT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"perf_hotspot_analyzer_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_cli_run_report(
    *,
    output_dir: Path,
    trace_id: str,
    started_at: str,
    total_ms: int,
    command: str,
    exit_status: str,
    errors: Sequence[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "run-report/v1",
        "trace_id": trace_id,
        "skill": "perf-hotspot-analyzer",
        "started_at": started_at,
        "total_ms": total_ms,
        "by_step": {command: total_ms},
        "input": {"command": command},
        "findings": {"total": 0, "by_kind": {}},
        "anchors": {"resolved": 0, "confidence_distribution": {}},
        "gate_decisions": [],
        "patches": {"diff-ready": 0, "needs-review": 0, "advisory-only": 0},
        "degradations": [],
        "exit_status": exit_status,
        "errors": list(errors),
    }
    (output_dir / "run-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
