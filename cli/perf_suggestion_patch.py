"""CLI for Skill B."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Sequence

from common.cli_base import (
    EXIT_FATAL,
    EXIT_INPUT_UNREADABLE,
    EXIT_SUCCESS,
    run_validate_cli,
)
from common.schema_validate import PERFORMANCE_FINDINGS, SUGGESTION_PATCH
from common.schema_validate import SchemaValidationError


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if args_list and args_list[0] == "validate":
        return _run_validate(args_list)

    parser = _build_parser()
    args = parser.parse_args(args_list)
    if args.command == "validate":
        return _run_validate(args_list)

    try:
        ingest = _load_ingest_module()
        renamed_map = json.loads(args.renamed_map) if args.renamed_map else None
        result = ingest.run_ingest(
            report_path=args.input,
            output_dir=args.output_dir,
            input_format=args.format,
            baseline_report=args.baseline_report,
            repo_root=args.repo_root,
            renamed_map=renamed_map,
            target_name=args.target_name,
            verbose=args.verbose,
        )
        print(result.patches_path)
        print(result.run_report_path)
        if result.patch_report_path is not None:
            print(result.patch_report_path)
        return EXIT_SUCCESS
    except (FileNotFoundError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INPUT_UNREADABLE
    except (json.JSONDecodeError, SchemaValidationError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_FATAL


def _run_validate(argv: Sequence[str]) -> int:
    return run_validate_cli(
        argv=argv,
        skill="perf-suggestion-patch",
        default_document_type=SUGGESTION_PATCH,
        allowed_document_types=[PERFORMANCE_FINDINGS, SUGGESTION_PATCH],
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="perf-suggestion-patch")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="Validate a JSON contract document.")

    analyze = subparsers.add_parser(
        "analyze",
        help="Run an ingest adapter and advisory-only gate.",
    )
    analyze.add_argument(
        "--input",
        required=True,
        help="Input report to ingest.",
    )
    analyze.add_argument(
        "--format",
        choices=[
            "auto",
            "analyzer-json",
            "google-benchmark",
            "folded-stacks",
            "generic-llm",
        ],
        default="auto",
        help="Input report format.",
    )
    analyze.add_argument(
        "--baseline-report",
        help="Optional Google Benchmark baseline report.",
    )
    analyze.add_argument(
        "--repo-root",
        help="Repository root used by external-report anchor search.",
    )
    analyze.add_argument(
        "--renamed-map",
        help="JSON object mapping renamed benchmark names for before/after comparison.",
    )
    analyze.add_argument(
        "--target-name",
        help="Optional target name for normalized external reports.",
    )
    analyze.add_argument(
        "--output-dir",
        default="out",
        help="Directory for patches.json, run-report.json, and trace JSONL.",
    )
    analyze.add_argument("--verbose", action="store_true", help="Enable DEBUG tracing.")
    return parser


def _load_ingest_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "perf-suggestion-patch"
        / "scripts"
        / "ingest.py"
    )
    spec = importlib.util.spec_from_file_location("perf_suggestion_patch_ingest", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load ingest module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    raise SystemExit(main())
