from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATE_PATH = ROOT / "workflows" / "perf-optimization-pipeline" / "orchestrate.py"


def load_orchestrate():
    spec = importlib.util.spec_from_file_location("mfinal_orchestrate", ORCHESTRATE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_non_interactive_never_invokes_apply_commit_or_push(tmp_path: Path) -> None:
    orchestrate = load_orchestrate()
    repo = tmp_path / "repo"
    repo.mkdir()
    git_dir = repo / ".git"
    git_dir.mkdir()
    sentinel = git_dir / "sentinel"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
        mode: b-only
        run_id: safety
        repo_root: {repo}
        output_dir: {tmp_path / "runs"}
        non_interactive: true
        b:
          input: input.json
          format: analyzer-json
          repo_root: {repo}
        """,
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_executor(argv, timeout_s):
        calls.append(list(argv))
        output_dir = Path(argv[argv.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "patches.json").write_text('{"patches":[]}\n', encoding="utf-8")
        (output_dir / "patch-report.md").write_text("# Patch Report\n", encoding="utf-8")
        return orchestrate.CommandResult(list(argv), 0, "", "", 1)

    result = orchestrate.run_pipeline(
        config_path=config,
        non_interactive=True,
        executor=fake_executor,
    )

    forbidden = {"git", "apply", "commit", "push"}
    assert calls
    assert all(not forbidden.intersection(call) for call in calls)
    assert sentinel.read_text(encoding="utf-8") == "unchanged\n"
    assert result.patches_path == tmp_path / "runs" / "safety" / "b_run" / "patches.json"


def test_stage_resume_skips_completed_a_and_gate1_after_b_failure(tmp_path: Path) -> None:
    orchestrate = load_orchestrate()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "bundle").mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
        mode: full
        run_id: resume
        repo_root: {repo}
        output_dir: {tmp_path / "runs"}
        non_interactive: true
        a:
          bundle_dir: bundle
        b:
          format: analyzer-json
          repo_root: {repo}
        """,
        encoding="utf-8",
    )
    first_calls: list[list[str]] = []

    def failing_executor(argv, timeout_s):
        first_calls.append(list(argv))
        if "perf_suggestion_patch" in argv:
            return orchestrate.CommandResult(list(argv), 1, "", "planned B failure", 1)
        write_fake_stage_outputs(argv)
        return orchestrate.CommandResult(list(argv), 0, "", "", 1)

    with pytest.raises(orchestrate.PipelineError):
        orchestrate.run_pipeline(
            config_path=config,
            non_interactive=True,
            executor=failing_executor,
        )

    state_path = tmp_path / "runs" / "resume" / "state.json"
    first_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert first_state["stages"]["a_report"]["status"] == "success"
    assert first_state["gates"]["gate_findings_review"]["status"] == "pass"
    assert first_state["stages"]["b_run"]["status"] == "failed"

    second_calls: list[list[str]] = []

    def succeeding_executor(argv, timeout_s):
        second_calls.append(list(argv))
        write_fake_stage_outputs(argv)
        return orchestrate.CommandResult(list(argv), 0, "", "", 1)

    result = orchestrate.run_pipeline(
        config_path=config,
        non_interactive=True,
        executor=succeeding_executor,
    )

    assert all("perf_hotspot_analyzer" not in call for call in second_calls)
    assert any("perf_suggestion_patch" in call for call in second_calls)
    final_state = json.loads(result.state_path.read_text(encoding="utf-8"))
    assert final_state["stages"]["b_run"]["status"] == "success"
    assert final_state["gates"]["gate_patch_approval"]["status"] == "pass"


def write_fake_stage_outputs(argv: list[str]) -> None:
    output_dir = Path(argv[argv.index("--output-dir") + 1])
    output_dir.mkdir(parents=True, exist_ok=True)
    if "analyze" in argv and "perf_hotspot_analyzer" in argv:
        output_path = Path(argv[argv.index("--output") + 1])
        output_path.write_text('{"schema_version":"postprocess/v1"}\n', encoding="utf-8")
        return
    if "report" in argv and "perf_hotspot_analyzer" in argv:
        (output_dir / "performance-findings.json").write_text(
            '{"findings":[{"kind":"function-hotspot"}]}\n',
            encoding="utf-8",
        )
        (output_dir / "analysis-report.md").write_text("# Analysis\n", encoding="utf-8")
        return
    if "perf_suggestion_patch" in argv:
        (output_dir / "patches.json").write_text(
            '{"patches":[{"status":"advisory-only"}]}\n',
            encoding="utf-8",
        )
        (output_dir / "patch-report.md").write_text("# Patch Report\n", encoding="utf-8")
