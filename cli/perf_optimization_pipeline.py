"""CLI for the non-triggerable perf optimization workflow."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from common.cli_base import (
    EXIT_FATAL,
    EXIT_INPUT_UNREADABLE,
    EXIT_SUCCESS,
    run_validate_cli,
)
from common.schema_validate import CAPTURE_BUNDLE, PERFORMANCE_FINDINGS, SUGGESTION_PATCH
from common.yaml_loader import load_yaml
from common.tracing import start_trace


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_SCRIPT = ROOT / "workflows" / "perf-optimization-pipeline" / "orchestrate.py"


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if args_list and args_list[0] == "validate":
        return _run_validate(args_list)

    parser = _build_parser()
    args = parser.parse_args(args_list)
    if args.command == "validate":
        return _run_validate(args_list)
    if args.command != "pipeline" or args.pipeline_command != "run":
        parser.error("expected: pipeline run --config <yaml>")

    trace_dir = _trace_output_dir(
        config_path=args.config,
        run_id=args.run_id,
        fallback=Path(args.output_dir or "out"),
    )
    tracer = start_trace(
        skill="perf-optimization-pipeline",
        output_dir=trace_dir,
        verbose=args.verbose,
    )
    try:
        orchestrate = _load_orchestrate()
        result = orchestrate.run_pipeline(
            config_path=args.config,
            mode_override=args.mode,
            non_interactive=args.non_interactive,
            run_id_override=args.run_id,
            tracer=tracer,
        )
        print(result.run_dir)
        print(result.run_report_path)
        if result.merged_report_path is not None:
            print(result.merged_report_path)
        return EXIT_SUCCESS
    except (FileNotFoundError, OSError) as exc:
        tracer.error("pipeline", "input_unreadable", error=str(exc))
        print(str(exc), file=sys.stderr)
        return EXIT_INPUT_UNREADABLE
    except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
        tracer.error("pipeline", "failed", error=str(exc))
        print(str(exc), file=sys.stderr)
        return EXIT_FATAL
    finally:
        tracer.close()


def _run_validate(argv: Sequence[str]) -> int:
    return run_validate_cli(
        argv=argv,
        skill="perf-optimization-pipeline",
        default_document_type=PERFORMANCE_FINDINGS,
        allowed_document_types=[PERFORMANCE_FINDINGS, SUGGESTION_PATCH, CAPTURE_BUNDLE],
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="perf-optimization-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="Validate a JSON contract document.")

    pipeline = subparsers.add_parser("pipeline", help="Run the workflow orchestrator.")
    pipeline_subparsers = pipeline.add_subparsers(dest="pipeline_command", required=True)
    run = pipeline_subparsers.add_parser("run", help="Run a configured pipeline.")
    run.add_argument("--config", required=True, help="Workflow config YAML.")
    run.add_argument(
        "--mode",
        choices=["full", "b-only", "a-only"],
        help="Override config mode.",
    )
    run.add_argument(
        "--non-interactive",
        action="store_true",
        help="Auto-pass workflow gates without applying or pushing patches.",
    )
    run.add_argument("--run-id", help="Use or resume a specific run id.")
    run.add_argument(
        "--output-dir",
        help="Fallback trace directory when config cannot be read.",
    )
    run.add_argument("--verbose", action="store_true", help="Enable DEBUG tracing.")
    return parser


def _load_orchestrate() -> Any:
    spec = importlib.util.spec_from_file_location(
        "perf_optimization_pipeline_orchestrate",
        WORKFLOW_SCRIPT,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load workflow orchestrator: {WORKFLOW_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _trace_output_dir(
    *,
    config_path: str | Path,
    run_id: str | None,
    fallback: Path,
) -> Path:
    try:
        config = load_yaml(config_path)
    except (OSError, ValueError):
        return fallback
    base = Path(config_path).resolve().parent
    repo_root = _resolve_path(config.get("repo_root") or base, base)
    output_dir = _resolve_path(config.get("output_dir") or ".perf-skill/runs", repo_root)
    trace_run_id = str(run_id or config.get("run_id") or "pending")
    return output_dir / trace_run_id


def _resolve_path(value: object, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return base / path


if __name__ == "__main__":
    raise SystemExit(main())
