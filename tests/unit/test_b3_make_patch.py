from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from common.schema_validate import SUGGESTION_PATCH, derive_effective_anchor, validate_document


ROOT = Path(__file__).resolve().parents[2]
MAKE_PATCH_PATH = ROOT / "skills" / "perf-suggestion-patch" / "scripts" / "make_patch.py"


def load_make_patch_module():
    spec = importlib.util.spec_from_file_location("b3_make_patch", MAKE_PATCH_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sample_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    (src / "hot.c").write_text(
        "int hot_loop(int n) {\n"
        "  int total = 0;\n"
        "  for (int i = 0; i < n; ++i) total += i;\n"
        "  return total;\n"
        "}\n",
        encoding="utf-8",
    )
    return repo


def performance_report(repo: Path) -> dict:
    return {
        "schema_version": "1.0",
        "report_types": ["hotspot-profile"],
        "target": {
            "name": "demo",
            "kind": "binary",
            "repo_root": str(repo),
            "platform": {"os": "linux", "arch": "x86_64"},
        },
        "source_reports": [
            {
                "id": "S1",
                "path": "performance-findings.json",
                "source_format": "analyzer-json",
                "parser": "structured",
                "confidence": 0.95,
            }
        ],
        "run_context": {
            "device": "host",
            "cpu_governor": "performance",
            "core_count": 4,
            "repeat_count": 1,
            "warmup_count": 0,
        },
        "profiling": {"tool": "perf", "events": ["cycles"], "callgraph_mode": "fp"},
        "findings": [
            {
                "id": "F001",
                "kind": "function-hotspot",
                "title": "hot_loop dominates samples",
                "source_ref": {
                    "source_id": "S1",
                    "locator": "$.findings[0]",
                    "label": "hot_loop",
                },
                "ownership": "owned",
                "actionability": "actionable",
                "evidence": {
                    "metric": "self_cpu_pct",
                    "value": 41.0,
                    "unit": "percent",
                    "rank": 1,
                    "hot_symbol": {
                        "symbol": "hot_loop",
                        "dso": "demo",
                        "ownership": "owned",
                    },
                },
                "code_anchors": [
                    {
                        "symbol": "hot_loop",
                        "file": "src/hot.c",
                        "line_start": 2,
                        "line_end": 4,
                        "language": "c",
                        "anchor_confidence": 0.86,
                        "resolution_method": "dwarf",
                    }
                ],
                "diagnosis": "Local hot loop is suitable for a micro-optimization.",
                "confidence": 0.9,
                "candidate_optimizations": [
                    {
                        "id": "O1",
                        "strategy": "hoist-loop-invariant",
                        "expected_impact": "medium",
                        "estimate": "~5%",
                        "confidence": 0.7,
                        "risk": "low",
                        "rationale": "Local loop.",
                    }
                ],
            }
        ],
        "provenance": {
            "generated_by": "test",
            "version": "1.0.0",
            "timestamp": "2026-06-02T00:00:00Z",
        },
    }


def test_make_patch_generates_diff_ready_atomic_patch(tmp_path: Path) -> None:
    make_patch = load_make_patch_module()
    repo = sample_repo(tmp_path)
    report = performance_report(repo)

    result = make_patch.build_patch_document(
        performance_report=report,
        output_dir=tmp_path / "out",
        generated_at="2026-06-02T00:00:00+00:00",
    )

    validate_document(result.suggestion_patch, document_type=SUGGESTION_PATCH)
    patch = result.suggestion_patch["patches"][0]
    assert patch["status"] == "diff-ready"
    assert patch["validation_status"] == "not-run"
    assert patch["measured_impact"] is None
    assert patch["chosen_anchor"] == derive_effective_anchor(report["findings"][0])
    assert patch["diff"].startswith("--- a/src/hot.c\n+++ b/src/hot.c\n")
    assert "PERF-SUGGESTION P001" in patch["diff"]
    assert result.gate_decisions[0]["decision"] == "diff-ready"
    assert (tmp_path / "out" / "patch-report.md").exists()

    patch_file = tmp_path / "generated.patch"
    patch_file.write_text(patch["diff"], encoding="utf-8")
    subprocess.run(
        ["git", "apply", "--check", str(patch_file)],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )


def test_make_patch_missing_anchor_stays_advisory_without_diff(tmp_path: Path) -> None:
    make_patch = load_make_patch_module()
    repo = sample_repo(tmp_path)
    report = performance_report(repo)
    report["findings"][0]["code_anchors"] = []
    report["findings"][0]["actionability"] = "informational"

    result = make_patch.build_patch_document(
        performance_report=report,
        output_dir=tmp_path / "out",
        generated_at="2026-06-02T00:00:00+00:00",
    )

    patch = result.suggestion_patch["patches"][0]
    assert patch["status"] == "advisory-only"
    assert "diff" not in patch
    assert "recommendation" in patch


def test_build_flag_policy_marks_package_wide_blast_radius(tmp_path: Path) -> None:
    make_patch = load_make_patch_module()
    repo = sample_repo(tmp_path)
    (repo / "CMakeLists.txt").write_text("add_executable(demo src/hot.c)\n", encoding="utf-8")
    report = performance_report(repo)
    finding = report["findings"][0]
    finding["kind"] = "binary-size-large"
    finding["evidence"] = {
        "metric": "section_bytes",
        "value": 131072,
        "unit": "bytes",
        "section": ".text",
        "file": "demo",
        "threshold": {"type": "absolute-bytes", "value": 65536, "reason": "large text"},
    }
    finding["code_anchors"] = [
        {
            "symbol": "CMakeLists",
            "file": "CMakeLists.txt",
            "line_start": 1,
            "line_end": 1,
            "language": "cmake",
            "anchor_confidence": 0.85,
            "resolution_method": "addr2line",
        }
    ]
    finding["candidate_optimizations"][0]["patch_category"] = "build-flag"
    report["report_types"] = ["binary-size"]
    report.pop("profiling")

    result = make_patch.build_patch_document(
        performance_report=report,
        output_dir=tmp_path / "out",
        generated_at="2026-06-02T00:00:00+00:00",
    )

    patch = result.suggestion_patch["patches"][0]
    assert patch["status"] == "needs-review"
    assert patch["patch_category"] == "build-flag"
    assert "may affect all files in package" in patch["files_touched_policy"]["reason"]
    assert patch["files_touched_policy"]["risk"] == "medium"


def test_deny_list_path_is_advisory_without_diff(tmp_path: Path) -> None:
    make_patch = load_make_patch_module()
    repo = sample_repo(tmp_path)
    git_dir = repo / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")
    report = performance_report(repo)
    report["findings"][0]["code_anchors"][0]["file"] = ".git/config"
    report["findings"][0]["code_anchors"][0]["line_start"] = 1
    report["findings"][0]["code_anchors"][0]["line_end"] = 1

    result = make_patch.build_patch_document(
        performance_report=report,
        output_dir=tmp_path / "out",
        generated_at="2026-06-02T00:00:00+00:00",
    )

    patch = result.suggestion_patch["patches"][0]
    assert patch["status"] == "advisory-only"
    assert "diff" not in patch
    assert patch["files_touched_policy"]["allowed"] is False
    assert "deny-list" in patch["files_touched_policy"]["reason"]


def test_allocation_reduction_local_reserve_can_emit_diff(tmp_path: Path) -> None:
    make_patch = load_make_patch_module()
    repo = sample_repo(tmp_path)
    report = performance_report(repo)
    candidate = report["findings"][0]["candidate_optimizations"][0]
    candidate["patch_category"] = "allocation-reduction"
    candidate["strategy"] = "reserve-local-vector"
    candidate["rationale"] = "Pure local reserve avoids repeated allocations."
    candidate["risk"] = "low"

    result = make_patch.build_patch_document(
        performance_report=report,
        output_dir=tmp_path / "out",
        generated_at="2026-06-02T00:00:00+00:00",
    )

    patch = result.suggestion_patch["patches"][0]
    assert patch["patch_category"] == "allocation-reduction"
    assert patch["status"] == "diff-ready"
    assert "diff" in patch


def test_allocation_reduction_shared_pool_is_advisory(tmp_path: Path) -> None:
    make_patch = load_make_patch_module()
    repo = sample_repo(tmp_path)
    report = performance_report(repo)
    candidate = report["findings"][0]["candidate_optimizations"][0]
    candidate["patch_category"] = "allocation-reduction"
    candidate["strategy"] = "shared-object-pool"
    candidate["rationale"] = "Use a shared cache with object pool ownership."
    candidate["risk"] = "high"

    result = make_patch.build_patch_document(
        performance_report=report,
        output_dir=tmp_path / "out",
        generated_at="2026-06-02T00:00:00+00:00",
    )

    patch = result.suggestion_patch["patches"][0]
    assert patch["status"] == "advisory-only"
    assert "diff" not in patch
    assert result.gate_decisions[0]["reason"] == "allocation-reduction-shared-ownership"


def test_api_semantic_change_never_emits_diff(tmp_path: Path) -> None:
    make_patch = load_make_patch_module()
    repo = sample_repo(tmp_path)
    report = performance_report(repo)
    report["findings"][0]["candidate_optimizations"][0]["patch_category"] = "api/semantic-change"

    result = make_patch.build_patch_document(
        performance_report=report,
        output_dir=tmp_path / "out",
        generated_at="2026-06-02T00:00:00+00:00",
    )

    patch = result.suggestion_patch["patches"][0]
    assert patch["status"] == "advisory-only"
    assert "diff" not in patch
    assert result.gate_decisions[0]["reason"] == "patch_category=api/semantic-change"


def test_patch_report_contains_each_required_section(tmp_path: Path) -> None:
    make_patch = load_make_patch_module()
    repo = sample_repo(tmp_path)
    report = performance_report(repo)

    result = make_patch.build_patch_document(
        performance_report=report,
        output_dir=tmp_path / "out",
        generated_at="2026-06-02T00:00:00+00:00",
    )

    patch_report = result.patch_report
    assert "## P001 -> F001" in patch_report
    assert "Expected impact" in patch_report
    assert "### Side Effects" in patch_report
    assert "### Apply" in patch_report
    assert "Do not apply, commit, or push automatically." in patch_report
    assert "### Verification" in patch_report
    assert "cmake --build build" in patch_report
