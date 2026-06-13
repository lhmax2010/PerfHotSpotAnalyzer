"""YAML loading facade with PyYAML first and simple_yaml fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from common.simple_yaml import SimpleYAMLError, load_yaml as _simple_load_yaml
from common.simple_yaml import loads_yaml as _simple_loads_yaml


_PYYAML_UNAVAILABLE = object()


def load_yaml(path: str | Path) -> dict[str, Any]:
    yaml_path = Path(path)
    parsed = loads_yaml(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise SimpleYAMLError(f"{yaml_path} must contain a mapping at the top level")
    return parsed


def loads_yaml(text: str) -> Any:
    parsed = _load_with_pyyaml(text)
    if parsed is not _PYYAML_UNAVAILABLE:
        return {} if parsed is None else parsed
    return _simple_loads_yaml(text)


def _load_with_pyyaml(text: str) -> Any:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return _PYYAML_UNAVAILABLE
    try:
        return yaml.safe_load(text)
    except Exception as exc:  # pragma: no cover - PyYAML exception type is optional.
        raise SimpleYAMLError(f"PyYAML failed to parse config: {exc}") from exc


def load_yaml_fallback_only(path: str | Path) -> dict[str, Any]:
    """Test helper for callers that must exercise the dependency-free parser."""

    return _simple_load_yaml(path)
