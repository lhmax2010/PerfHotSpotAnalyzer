"""M0 CLI skeleton for Skill B."""

from __future__ import annotations

from typing import Sequence

from common.cli_base import run_validate_cli
from common.schema_validate import PERFORMANCE_FINDINGS, SUGGESTION_PATCH


def main(argv: Sequence[str] | None = None) -> int:
    return run_validate_cli(
        argv=argv,
        skill="perf-suggestion-patch",
        default_document_type=SUGGESTION_PATCH,
        allowed_document_types=[PERFORMANCE_FINDINGS, SUGGESTION_PATCH],
    )


if __name__ == "__main__":
    raise SystemExit(main())
