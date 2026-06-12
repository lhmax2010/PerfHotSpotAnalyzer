from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from integrations.compiling_agent.adapter import PerfSkillCLIAdapter


def test_compiling_agent_analyze_success(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        assert kwargs["cwd"] == tmp_path
        assert kwargs["timeout"] == 7
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="/tmp/run\n/tmp/run/run-report.json\n/tmp/run/merged-report.md\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = PerfSkillCLIAdapter(repo_root=tmp_path, default_timeout_s=7)

    result = adapter.analyze(config_path="config.yaml", mode="b-only")

    assert result["status"] == "success"
    assert result["exit_code"] == 0
    assert result["artifacts"]["run_dir"] == "/tmp/run"
    assert "--non-interactive" in result["command"]


@pytest.mark.parametrize("returncode", [1, 2, 3])
def test_compiling_agent_analyze_non_zero_degrades(
    monkeypatch,
    tmp_path: Path,
    returncode: int,
) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=returncode,
            stdout="",
            stderr="failure",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = PerfSkillCLIAdapter(repo_root=tmp_path)

    result = adapter.analyze(config_path="config.yaml", non_interactive=False)

    assert result["status"] == "degraded"
    assert result["exit_code"] == returncode
    assert result["degraded_reason"] == f"cli exited with {returncode}"
    assert "--non-interactive" not in result["command"]


def test_compiling_agent_analyze_timeout_degrades(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=3, output=b"partial", stderr=b"late")

    monkeypatch.setattr(subprocess, "run", fake_run)
    adapter = PerfSkillCLIAdapter(repo_root=tmp_path)

    result = adapter.analyze(config_path="config.yaml", timeout_s=3)

    assert result["status"] == "degraded"
    assert result["exit_code"] == 124
    assert result["degraded_reason"] == "timeout after 3s"
    assert result["stdout"] == "partial"
    assert result["stderr"] == "late"


def test_compiling_agent_apply_is_review_only(tmp_path: Path) -> None:
    adapter = PerfSkillCLIAdapter(repo_root=tmp_path)

    result = adapter.apply(patches_path="patches.json")

    assert result["status"] == "degraded"
    assert "review-only" in result["degraded_reason"]
    assert result["artifacts"]["patches"] == "patches.json"
