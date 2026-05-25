from __future__ import annotations

import ast
from pathlib import Path


def test_skills_do_not_import_each_other() -> None:
    repo = Path(__file__).resolve().parents[2]
    analyzer_root = repo / "skills" / "perf-hotspot-analyzer"
    patch_root = repo / "skills" / "perf-suggestion-patch"

    forbidden = {
        analyzer_root: "perf_suggestion_patch",
        patch_root: "perf_hotspot_analyzer",
    }
    for root, forbidden_name in forbidden.items():
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                assert all(not name.startswith(forbidden_name) for name in names)
