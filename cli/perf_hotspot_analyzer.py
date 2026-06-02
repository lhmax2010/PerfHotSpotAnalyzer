"""M0 CLI skeleton for Skill A."""

from __future__ import annotations

from typing import Sequence

from common.cli_base import run_validate_cli
from common.schema_validate import CAPTURE_BUNDLE, PERFORMANCE_FINDINGS


def main(argv: Sequence[str] | None = None) -> int:
    return run_validate_cli(
        argv=argv,
        skill="perf-hotspot-analyzer",
        default_document_type=PERFORMANCE_FINDINGS,
        allowed_document_types=[PERFORMANCE_FINDINGS, CAPTURE_BUNDLE],
    )


if __name__ == "__main__":
    raise SystemExit(main())
