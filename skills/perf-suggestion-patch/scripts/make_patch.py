"""Suggestion patch assembly for Skill B."""

from __future__ import annotations

import difflib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from common import schema_validate


ANCHOR_GATE_THRESHOLD = 0.70


@dataclass(frozen=True)
class PatchBuildResult:
    """Generated suggestion patch contract plus human-readable report."""

    suggestion_patch: dict[str, Any]
    gate_decisions: list[dict[str, Any]]
    patch_report: str


def build_patch_document(
    *,
    performance_report: dict[str, Any],
    output_dir: str | Path,
    build_cmd: str | None = None,
    test_cmd: str | None = None,
    benchmark_cmd: str | None = None,
    generated_at: str | None = None,
) -> PatchBuildResult:
    """Build a suggestion-patch document from performance findings."""

    schema_validate.validate_document(
        performance_report,
        document_type=schema_validate.PERFORMANCE_FINDINGS,
        skill="perf-suggestion-patch",
    )
    repo_root = _repo_root(performance_report)
    patches = []
    gate_decisions = []
    for index, finding in enumerate(performance_report.get("findings", []), start=1):
        patch, decision = _build_patch(
            index=index,
            finding=finding,
            repo_root=repo_root,
            build_cmd=build_cmd,
            test_cmd=test_cmd,
            benchmark_cmd=benchmark_cmd,
        )
        patches.append(patch)
        gate_decisions.append(decision)

    suggestion_patch = {
        "schema_version": "1.0",
        "source_reports": deepcopy(performance_report.get("source_reports", [])),
        "patches": patches,
        "apply_instructions": (
            "Review generated patches manually. Do not apply, commit, or push "
            "runtime-generated diffs automatically."
        ),
        "provenance": {
            "generated_by": "perf-suggestion-patch.make_patch",
            "version": "1.0.0-b3",
            "timestamp": generated_at or datetime.now(UTC).isoformat(),
        },
    }
    schema_validate.validate_document(
        suggestion_patch,
        document_type=schema_validate.SUGGESTION_PATCH,
        skill="perf-suggestion-patch",
    )
    patch_report = build_patch_report(suggestion_patch)
    _write_patch_artifacts(output_dir, suggestion_patch, patch_report)
    return PatchBuildResult(
        suggestion_patch=suggestion_patch,
        gate_decisions=gate_decisions,
        patch_report=patch_report,
    )


def build_patch_report(suggestion_patch: dict[str, Any]) -> str:
    """Render a concise human-readable patch report."""

    lines = ["# Suggestion Patch Report", ""]
    for patch in suggestion_patch.get("patches", []):
        lines.extend(
            [
                f"## {patch['id']} -> {patch['finding_id']}",
                "",
                f"- Status: {patch['status']}",
                f"- Category: {patch['patch_category']}",
                f"- Strategy: {patch.get('strategy', 'unknown')}",
                f"- Expected impact: {patch['expected_impact'].get('level', 'unknown')} "
                f"({patch['expected_impact'].get('estimate', 'estimate unavailable')}, "
                f"confidence {patch['expected_impact'].get('confidence', 0)})",
                f"- Risk: {patch['risk'].get('level', 'unknown')}",
                f"- Files touched: {', '.join(patch.get('files_touched', [])) or 'none'}",
                f"- Files policy: {patch['files_touched_policy']['reason']} "
                f"(risk {patch['files_touched_policy']['risk']})",
                f"- Rationale: {patch['rationale']}",
                "",
                "### Verification",
                "",
            ]
        )
        plan = patch.get("verification_plan", {})
        lines.extend(
            [
                f"- Build: {plan.get('build_cmd')}",
                f"- Test: {plan.get('test_cmd')}",
                f"- Benchmark: {plan.get('benchmark_cmd')}",
                "",
            ]
        )
        if patch.get("status") == "advisory-only":
            recommendation = patch.get("recommendation", {})
            lines.extend(
                [
                    "### Recommendation",
                    "",
                    recommendation.get("idea", "Review the finding manually."),
                    "",
                ]
            )
        else:
            lines.extend(["### Diff", "", "```diff", patch.get("diff", ""), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def _build_patch(
    *,
    index: int,
    finding: dict[str, Any],
    repo_root: Path | None,
    build_cmd: str | None,
    test_cmd: str | None,
    benchmark_cmd: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    chosen_anchor = _chosen_anchor(finding)
    candidate = _first_candidate(finding)
    category = _infer_patch_category(finding, candidate)
    strategy = str(candidate.get("strategy", "review-optimization"))
    base = _base_patch(
        index=index,
        finding=finding,
        category=category,
        strategy=strategy,
        candidate=candidate,
        build_cmd=build_cmd,
        test_cmd=test_cmd,
        benchmark_cmd=benchmark_cmd,
    )

    reasons = _basic_advisory_reasons(finding, chosen_anchor)
    if reasons:
        patch = _advisory_patch(base, finding, chosen_anchor, reasons)
        return patch, _gate_decision(finding, patch, chosen_anchor, reasons)

    diff_result = _generate_unified_diff(
        patch_id=base["id"],
        finding=finding,
        chosen_anchor=chosen_anchor,
        repo_root=repo_root,
        strategy=strategy,
    )
    if diff_result is None:
        reasons = ["anchor-file-unavailable"]
        patch = _advisory_patch(base, finding, chosen_anchor, reasons)
        return patch, _gate_decision(finding, patch, chosen_anchor, reasons)

    relative_file, diff_text = diff_result
    files_policy = evaluate_files_touched_policy([relative_file], category)
    if not files_policy["allowed"]:
        reasons = [files_policy["reason"]]
        patch = _advisory_patch(base, finding, chosen_anchor, reasons)
        patch["files_touched_policy"] = files_policy
        return patch, _gate_decision(finding, patch, chosen_anchor, reasons)

    patch = deepcopy(base)
    patch.update(
        {
            "chosen_anchor": chosen_anchor,
            "diff": diff_text,
            "files_touched": [relative_file],
            "files_touched_policy": files_policy,
            "status": "diff-ready",
        }
    )
    return patch, _gate_decision(finding, patch, chosen_anchor, [])


def evaluate_files_touched_policy(files: list[str], patch_category: str) -> dict[str, Any]:
    """Evaluate DESIGN file allow/deny policy for generated diffs."""

    denied = [file for file in files if _is_denied_path(file)]
    if denied:
        return {
            "allowed": False,
            "reason": f"deny-list path is not patchable: {', '.join(denied)}",
            "risk": "high",
        }

    not_allowed = [file for file in files if not _is_default_allowed_path(file)]
    if not_allowed:
        return {
            "allowed": False,
            "reason": f"path is outside default allow list: {', '.join(not_allowed)}",
            "risk": "medium",
        }

    if patch_category == "build-flag":
        return {
            "allowed": True,
            "reason": "build-flag change may affect all files in package",
            "risk": "medium",
        }

    return {
        "allowed": True,
        "reason": "Default source path and local code change.",
        "risk": "low",
    }


def _base_patch(
    *,
    index: int,
    finding: dict[str, Any],
    category: str,
    strategy: str,
    candidate: dict[str, Any],
    build_cmd: str | None,
    test_cmd: str | None,
    benchmark_cmd: str | None,
) -> dict[str, Any]:
    return {
        "id": f"P{index:03d}",
        "finding_id": finding["id"],
        "source_ref": deepcopy(finding["source_ref"]),
        "patch_category": category,
        "strategy": strategy,
        "files_touched": [],
        "files_touched_policy": {
            "allowed": False,
            "reason": "No patchable file selected.",
            "risk": "medium",
        },
        "expected_impact": {
            "level": str(candidate.get("expected_impact", "unknown")),
            "estimate": str(candidate.get("estimate", "estimated impact; not measured")),
            "confidence": float(candidate.get("confidence", finding.get("confidence", 0.0))),
        },
        "measured_impact": None,
        "side_effects": {
            "runtime_memory": "unknown",
            "binary_size": "unknown",
            "startup_time": "unknown",
            "maintainability": "review required",
        },
        "risk": {
            "level": str(candidate.get("risk", "medium")),
            "notes": "Generated suggestion requires human review.",
        },
        "rationale": str(finding.get("diagnosis", finding.get("title", finding["id"]))),
        "verification_plan": {
            "build_cmd": build_cmd or "cmake --build build",
            "test_cmd": test_cmd or "ctest --test-dir build",
            "benchmark_cmd": benchmark_cmd or "rerun the original benchmark or workload",
            "manual_steps": ["Review the diff before applying it."],
            "required": True,
        },
        "validation_status": "not-run",
    }


def _advisory_patch(
    base: dict[str, Any],
    finding: dict[str, Any],
    chosen_anchor: dict[str, Any] | None,
    reasons: list[str],
) -> dict[str, Any]:
    patch = deepcopy(base)
    patch.update(
        {
            "recommendation": {
                "suggested_locations": _suggested_locations(chosen_anchor, finding),
                "idea": _recommendation_idea(finding, reasons),
                "risk": patch["risk"]["level"],
            },
            "files_touched": [],
            "files_touched_policy": {
                "allowed": False,
                "reason": "; ".join(reasons),
                "risk": patch["risk"]["level"],
            },
            "status": "advisory-only",
        }
    )
    return patch


def _basic_advisory_reasons(
    finding: dict[str, Any],
    chosen_anchor: dict[str, Any] | None,
) -> list[str]:
    reasons = []
    if finding.get("actionability") != "actionable":
        reasons.append(f"actionability={finding.get('actionability', 'unknown')}")
    if chosen_anchor is None:
        reasons.append("effective_anchor=null")
    elif _anchor_confidence(chosen_anchor) < ANCHOR_GATE_THRESHOLD:
        reasons.append(f"effective_anchor_confidence={_anchor_confidence(chosen_anchor)} < 0.70")
    if finding.get("kind") == "benchmark-latency" and not finding.get("perf_budget"):
        reasons.append("benchmark-latency-without-perf-budget")
    return reasons


def _generate_unified_diff(
    *,
    patch_id: str,
    finding: dict[str, Any],
    chosen_anchor: dict[str, Any],
    repo_root: Path | None,
    strategy: str,
) -> tuple[str, str] | None:
    if repo_root is None:
        return None
    relative_file = str(chosen_anchor.get("file", ""))
    if not relative_file:
        return None
    file_path = repo_root / relative_file
    if not file_path.exists() or not file_path.is_file():
        return None

    original = file_path.read_text(encoding="utf-8").splitlines()
    line_index = max(0, min(int(chosen_anchor.get("line_start", 1)) - 1, len(original)))
    comment = _suggestion_comment(file_path, patch_id, finding, strategy)
    modified = original[:line_index] + [comment] + original[line_index:]
    diff_lines = difflib.unified_diff(
        original,
        modified,
        fromfile=f"a/{relative_file}",
        tofile=f"b/{relative_file}",
        lineterm="",
    )
    diff_text = "\n".join(diff_lines) + "\n"
    return relative_file, diff_text


def _suggestion_comment(
    file_path: Path,
    patch_id: str,
    finding: dict[str, Any],
    strategy: str,
) -> str:
    text = f"PERF-SUGGESTION {patch_id}: review {strategy} for {finding['id']}"
    if file_path.suffix.lower() in {".cmake", ".txt"} or file_path.name == "CMakeLists.txt":
        return f"# {text}"
    return f"// {text}"


def _is_denied_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    parts = [part for part in normalized.split("/") if part]
    lowered = normalized.lower()
    if ".git" in parts:
        return True
    if lowered.endswith(".lock"):
        return True
    if any(part in {"secrets", "secret", "credentials", ".ssh"} for part in parts):
        return True
    if any(marker in lowered for marker in ("password", "credential", "secret", "token")):
        return True
    if any(part in {"build", "dist", "out", "generated", "__pycache__"} for part in parts):
        return True
    binary_suffixes = {
        ".a",
        ".bin",
        ".dll",
        ".dylib",
        ".elf",
        ".exe",
        ".o",
        ".png",
        ".so",
        ".zip",
    }
    return Path(normalized).suffix.lower() in binary_suffixes


def _is_default_allowed_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("/")
    if normalized.startswith(("src/", "include/")):
        return True
    if normalized == "CMakeLists.txt":
        return True
    if normalized.startswith("packaging/") and normalized.endswith(".spec"):
        return True
    return False


def _chosen_anchor(finding: dict[str, Any]) -> dict[str, Any] | None:
    anchor = schema_validate.derive_effective_anchor(finding)
    return deepcopy(anchor) if anchor is not None else None


def _anchor_confidence(anchor: dict[str, Any]) -> float:
    confidence = anchor.get("anchor_confidence")
    if isinstance(confidence, int | float):
        return float(confidence)
    return 0.0


def _first_candidate(finding: dict[str, Any]) -> dict[str, Any]:
    candidates = finding.get("candidate_optimizations", [])
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        return candidates[0]
    return {}


def _infer_patch_category(finding: dict[str, Any], candidate: dict[str, Any]) -> str:
    category = candidate.get("patch_category")
    if category:
        return str(category)
    strategy = str(candidate.get("strategy", "")).lower()
    if "allocation" in strategy or "reserve" in strategy:
        return "allocation-reduction"
    if finding.get("kind") in {"binary-size-large", "binary-size-regression"}:
        return "build-flag"
    return "local-micro-optimization"


def _suggested_locations(
    chosen_anchor: dict[str, Any] | None,
    finding: dict[str, Any],
) -> list[str]:
    if chosen_anchor and chosen_anchor.get("file"):
        line = chosen_anchor.get("line_start")
        suffix = f":{line}" if isinstance(line, int) else ""
        return [f"{chosen_anchor['file']}{suffix}"]
    source_ref = finding.get("source_ref", {})
    if isinstance(source_ref, dict) and source_ref.get("label"):
        return [str(source_ref["label"])]
    return []


def _recommendation_idea(finding: dict[str, Any], reasons: list[str]) -> str:
    title = str(finding.get("title", finding["id"]))
    return f"{title}: advisory-only because {', '.join(reasons)}."


def _gate_decision(
    finding: dict[str, Any],
    patch: dict[str, Any],
    chosen_anchor: dict[str, Any] | None,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "finding_id": finding["id"],
        "decision": patch["status"],
        "reason": "; ".join(reasons) if reasons else patch["status"],
        "actionability": finding.get("actionability", "unknown"),
        "effective_anchor": chosen_anchor,
        "anchor_confidence": _anchor_confidence(chosen_anchor) if chosen_anchor else None,
        "patch_category": patch["patch_category"],
    }


def _repo_root(performance_report: dict[str, Any]) -> Path | None:
    repo_root = performance_report.get("target", {}).get("repo_root")
    if not repo_root:
        return None
    return Path(str(repo_root))


def _write_patch_artifacts(
    output_dir: str | Path,
    suggestion_patch: dict[str, Any],
    patch_report: str,
) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "patches.json").write_text(
        json.dumps(suggestion_patch, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_path / "patch-report.md").write_text(patch_report, encoding="utf-8")
