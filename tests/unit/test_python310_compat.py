from __future__ import annotations

import ast
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOTS = [
    ROOT / "common",
    ROOT / "cli",
    ROOT / "perf_hotspot_analyzer",
    ROOT / "perf_suggestion_patch",
    ROOT / "perf_optimization_pipeline",
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts",
    ROOT / "skills" / "perf-suggestion-patch" / "scripts",
    ROOT / "workflows" / "perf-optimization-pipeline",
]
ENTRYPOINT_MODULES = [
    "cli.perf_hotspot_analyzer",
    "cli.perf_suggestion_patch",
    "cli.perf_optimization_pipeline",
    "perf_hotspot_analyzer.__main__",
    "perf_suggestion_patch.__main__",
    "perf_optimization_pipeline.__main__",
]


def iter_python_sources() -> list[Path]:
    paths: list[Path] = []
    for root in SOURCE_ROOTS:
        if not root.exists():
            continue
        paths.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(set(paths))


def test_entrypoints_import_without_datetime_utc() -> None:
    for module_name in ENTRYPOINT_MODULES:
        importlib.import_module(module_name)


def test_no_python311_only_features_in_runtime_sources() -> None:
    try_star_type = getattr(ast, "TryStar", ())
    for path in iter_python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "datetime":
                imported = {alias.name for alias in node.names}
                assert "UTC" not in imported, str(path)
            if isinstance(node, ast.Attribute):
                assert not (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "datetime"
                    and node.attr == "UTC"
                ), str(path)
            if isinstance(node, ast.Import):
                assert "tomllib" not in {alias.name for alias in node.names}, str(path)
            if isinstance(node, ast.ImportFrom):
                assert not (node.module == "typing" and "Self" in {alias.name for alias in node.names}), str(path)
            if try_star_type and isinstance(node, try_star_type):
                raise AssertionError(str(path))
