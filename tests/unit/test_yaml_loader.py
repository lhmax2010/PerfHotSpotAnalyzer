from __future__ import annotations

from pathlib import Path

from common import yaml_loader


def test_yaml_loader_prefers_pyyaml_when_available(monkeypatch) -> None:
    monkeypatch.setattr(yaml_loader, "_load_with_pyyaml", lambda text: {"engine": "pyyaml"})

    assert yaml_loader.loads_yaml("engine: fallback") == {"engine": "pyyaml"}


def test_yaml_loader_falls_back_to_simple_yaml(monkeypatch) -> None:
    monkeypatch.setattr(
        yaml_loader,
        "_load_with_pyyaml",
        lambda text: yaml_loader._PYYAML_UNAVAILABLE,
    )

    assert yaml_loader.loads_yaml("name: host\nitems:\n  - one\n  - two\n") == {
        "name": "host",
        "items": ["one", "two"],
    }


def test_runtime_callers_use_yaml_loader_facade() -> None:
    runtime_roots = [
        Path("common"),
        Path("cli"),
        Path("skills/perf-hotspot-analyzer/scripts"),
        Path("workflows/perf-optimization-pipeline"),
    ]
    for root in runtime_roots:
        for path in root.rglob("*.py"):
            if path.name in {"simple_yaml.py", "yaml_loader.py"}:
                continue
            text = path.read_text(encoding="utf-8")
            assert "from common.simple_yaml import load_yaml" not in text, str(path)
