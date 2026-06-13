"""Shared argparse and exit-code handling for the M0 CLI entrypoints."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from common import schema_validate
from common.schema_validate import SchemaValidationError
from common.tracing import start_trace


EXIT_SUCCESS = 0
EXIT_FATAL = 1
EXIT_USAGE = 2
EXIT_INPUT_UNREADABLE = 3
EXIT_TIMEOUT = 124


def run_validate_cli(
    *,
    argv: Sequence[str] | None = None,
    skill: str,
    default_document_type: str,
    allowed_document_types: Sequence[str],
) -> int:
    parser = _build_parser(
        skill=skill,
        default_document_type=default_document_type,
        allowed_document_types=allowed_document_types,
    )
    args = parser.parse_args(argv)
    if args.command != "validate":
        parser.error("only the validate subcommand is available in M0")

    started = time.monotonic()
    output_dir = Path(args.output_dir)
    tracer = start_trace(skill=skill, output_dir=output_dir, verbose=args.verbose)
    exit_code = EXIT_SUCCESS
    status = "success"
    errors: list[str] = []

    try:
        tracer.info(
            "validate",
            "start",
            document=args.input,
            document_type=args.document_type,
        )
        schema_validate.validate_file(
            args.input,
            document_type=args.document_type,
            schema_path=args.schema,
            skill=skill,
        )
        tracer.info("validate", "success")
    except FileNotFoundError as exc:
        exit_code = EXIT_INPUT_UNREADABLE
        status = "input-unreadable"
        errors.append(str(exc))
        tracer.error("validate", "input_unreadable", error=str(exc))
    except OSError as exc:
        exit_code = EXIT_INPUT_UNREADABLE
        status = "input-unreadable"
        errors.append(str(exc))
        tracer.error("validate", "input_unreadable", error=str(exc))
    except (json.JSONDecodeError, SchemaValidationError, ValueError) as exc:
        exit_code = EXIT_FATAL
        status = "validation-failed"
        errors.append(str(exc))
        tracer.error("validate", "failed", error=str(exc))
    finally:
        total_ms = int((time.monotonic() - started) * 1000)
        _write_run_report(
            output_dir=output_dir,
            trace_id=tracer.trace_id,
            skill=skill,
            started_at=datetime.now(timezone.utc).isoformat(),
            total_ms=total_ms,
            input_path=args.input,
            document_type=args.document_type,
            exit_status=status,
            errors=errors,
        )
        tracer.close()

    for error in errors:
        print(error, file=sys.stderr)
    return exit_code


def _build_parser(
    *,
    skill: str,
    default_document_type: str,
    allowed_document_types: Sequence[str],
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=skill)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate a JSON contract document.")
    validate.add_argument("--input", required=True, help="JSON file to validate.")
    validate.add_argument(
        "--document-type",
        choices=list(allowed_document_types),
        default=default_document_type,
        help="Contract type to validate.",
    )
    validate.add_argument("--schema", help="Override schema path.")
    validate.add_argument(
        "--output-dir",
        default="out",
        help="Directory for run-report.json and run-<trace_id>.jsonl.",
    )
    validate.add_argument("--verbose", action="store_true", help="Enable DEBUG tracing.")
    return parser


def _write_run_report(
    *,
    output_dir: Path,
    trace_id: str,
    skill: str,
    started_at: str,
    total_ms: int,
    input_path: str,
    document_type: str,
    exit_status: str,
    errors: Sequence[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "run-report/v1",
        "trace_id": trace_id,
        "skill": skill,
        "started_at": started_at,
        "total_ms": total_ms,
        "by_step": {"validate": total_ms},
        "input": {"path": input_path, "document_type": document_type},
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
