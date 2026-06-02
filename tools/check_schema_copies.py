"""Check canonical schema files match skill-local release copies."""

from __future__ import annotations

import hashlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_COPY_GROUPS = {
    "performance-findings.schema.json": [
        REPO_ROOT / "skills/perf-hotspot-analyzer/schemas/performance-findings.schema.json",
        REPO_ROOT / "skills/perf-suggestion-patch/schemas/performance-findings.schema.json",
    ],
    "suggestion-patch.schema.json": [
        REPO_ROOT / "skills/perf-suggestion-patch/schemas/suggestion-patch.schema.json",
    ],
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures: list[str] = []
    for schema_name, copies in SCHEMA_COPY_GROUPS.items():
        canonical = REPO_ROOT / "common" / "schemas" / schema_name
        canonical_hash = sha256(canonical)
        for copy in copies:
            copy_hash = sha256(copy)
            if copy_hash != canonical_hash:
                failures.append(
                    f"{copy.relative_to(REPO_ROOT)} sha256={copy_hash} "
                    f"does not match common/schemas/{schema_name} sha256={canonical_hash}"
                )

    if failures:
        print("\n".join(failures))
        return 1

    for schema_name in SCHEMA_COPY_GROUPS:
        canonical = REPO_ROOT / "common" / "schemas" / schema_name
        print(f"{schema_name} sha256={sha256(canonical)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
