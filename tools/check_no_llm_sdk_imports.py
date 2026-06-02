"""Fail when production code imports an LLM SDK."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOTS = [
    "common",
    "skills",
    "workflows",
    "cli",
    "mcp",
    "integrations",
]
LLM_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(openai|anthropic|google\.generativeai|cohere)\b"
)


def iter_python_files(roots: Iterable[Path]) -> Iterable[Path]:
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            yield root
            continue
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            relative_parts = path.relative_to(REPO_ROOT).parts if path.is_relative_to(REPO_ROOT) else path.parts
            if "tests" in relative_parts:
                continue
            yield path


def scan_paths(roots: Sequence[Path]) -> list[str]:
    findings: list[str] = []
    for path in iter_python_files(roots):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = LLM_IMPORT_RE.search(line)
            if match:
                findings.append(f"{path}:{line_number}: forbidden LLM SDK import: {line.strip()}")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan production code for LLM SDK imports.")
    parser.add_argument(
        "roots",
        nargs="*",
        help="Optional roots to scan. Defaults to common/skills/workflows/cli/mcp/integrations.",
    )
    args = parser.parse_args(argv)

    roots = [Path(root) for root in args.roots] if args.roots else [REPO_ROOT / root for root in DEFAULT_ROOTS]
    findings = scan_paths(roots)
    if findings:
        print("\n".join(findings))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
