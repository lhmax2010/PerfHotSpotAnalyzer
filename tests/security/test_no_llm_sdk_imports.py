from __future__ import annotations

import subprocess
from pathlib import Path

from tools.check_no_llm_sdk_imports import main

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_llm_sdk_scan_allows_current_production_tree() -> None:
    assert main([]) == 0


def test_llm_sdk_scan_fails_on_intentional_violation(tmp_path: Path) -> None:
    bad_root = tmp_path / "common"
    bad_root.mkdir()
    (bad_root / "bad.py").write_text("from openai import OpenAI\n", encoding="utf-8")

    assert main([str(bad_root)]) == 1


def test_grep_script_fails_on_intentional_violation(tmp_path: Path) -> None:
    bad_root = tmp_path / "common"
    bad_root.mkdir()
    (bad_root / "bad.py").write_text("import anthropic\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / "check_no_llm_sdk_imports.sh"), str(bad_root)],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "import anthropic" in result.stdout
