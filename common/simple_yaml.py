"""Small YAML reader for repository-owned configuration files.

The A1 runtime only needs a conservative subset of YAML: dictionaries,
lists, strings, booleans, numbers, and nulls.  Keeping that subset local
avoids adding a dependency for device profiles, capture jobs, and ownership
profiles.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SimpleYAMLError(ValueError):
    """Raised when a file uses YAML features outside the supported subset."""


def load_yaml(path: str | Path) -> dict[str, Any]:
    yaml_path = Path(path)
    text = yaml_path.read_text(encoding="utf-8")
    parsed = loads_yaml(text)
    if not isinstance(parsed, dict):
        raise SimpleYAMLError(f"{yaml_path} must contain a mapping at the top level")
    return parsed


def loads_yaml(text: str) -> Any:
    lines = _preprocess(text)
    if not lines:
        return {}
    value, next_index = _parse_block(lines, 0, lines[0][0])
    if next_index != len(lines):
        raise SimpleYAMLError("unexpected trailing YAML content")
    return value


def _preprocess(text: str) -> list[tuple[int, str]]:
    processed: list[tuple[int, str]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
        without_comment = _strip_comment(raw).rstrip()
        if not without_comment.strip():
            continue
        indent = len(without_comment) - len(without_comment.lstrip(" "))
        if "\t" in without_comment[:indent]:
            raise SimpleYAMLError(f"line {line_number}: tabs are not supported")
        processed.append((indent, without_comment[indent:]))
    return processed


def _parse_block(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, content = lines[index]
    if current_indent != indent:
        raise SimpleYAMLError("inconsistent indentation")
    if content.startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise SimpleYAMLError(f"unexpected nested mapping line: {content}")
        if content.startswith("- "):
            break
        if ":" not in content:
            raise SimpleYAMLError(f"expected key: value line, got: {content}")
        key, raw_value = content.split(":", 1)
        key = key.strip()
        if not key:
            raise SimpleYAMLError("empty keys are not supported")
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key] = _parse_scalar(raw_value)
            continue
        if index >= len(lines) or lines[index][0] <= indent:
            result[key] = {}
            continue
        nested, index = _parse_block(lines, index, lines[index][0])
        result[key] = nested
    return result, index


def _parse_list(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, content = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise SimpleYAMLError(f"unexpected nested list line: {content}")
        if not content.startswith("- "):
            break
        item = content[2:].strip()
        index += 1
        if item:
            if ":" in item and not _is_quoted(item):
                key, raw_value = item.split(":", 1)
                entry: dict[str, Any] = {key.strip(): _parse_scalar(raw_value.strip())}
                if index < len(lines) and lines[index][0] > indent:
                    nested, index = _parse_mapping(lines, index, lines[index][0])
                    entry.update(nested)
                result.append(entry)
            else:
                result.append(_parse_scalar(item))
            continue
        if index >= len(lines) or lines[index][0] <= indent:
            result.append(None)
            continue
        nested, index = _parse_block(lines, index, lines[index][0])
        result.append(nested)
    return result, index


def _parse_scalar(raw: str) -> Any:
    if raw == "[]":
        return []
    if raw == "{}":
        return {}
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if _is_quoted(raw):
        return raw[1:-1]
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none", "~"}:
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _strip_comment(raw: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(raw):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            if index == 0 or raw[index - 1].isspace():
                return raw[:index]
    return raw


def _is_quoted(raw: str) -> bool:
    return (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    )
