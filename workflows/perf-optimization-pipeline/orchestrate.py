"""Workflow orchestrator for perf-optimization-pipeline.

This module is intentionally not a triggerable skill.  It coordinates the
already-implemented Skill A and Skill B CLIs and writes review artifacts under a
workflow run directory.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from common.yaml_loader import load_yaml
from common.tracing import TraceLogger


VALID_MODES = {"full", "b-only", "a-only"}
STATE_FILE = "state.json"


class PipelineError(RuntimeError):
    """Raised when a workflow stage cannot complete."""


@dataclass(frozen=True)
class CommandResult:
    """Completed subprocess result captured for trace and state files."""

    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    elapsed_ms: int


@dataclass(frozen=True)
class PipelineResult:
    """High-level paths produced by a workflow run."""

    run_id: str
    run_dir: Path
    mode: str
    state_path: Path
    performance_findings_path: Path | None
    patches_path: Path | None
    merged_report_path: Path | None
    run_report_path: Path


Executor = Callable[[Sequence[str], int], CommandResult]


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a workflow YAML config."""

    config = load_yaml(path)
    if not isinstance(config, dict):
        raise ValueError("pipeline config must be a mapping")
    return config


def run_pipeline(
    *,
    config_path: str | Path,
    mode_override: str | None = None,
    non_interactive: bool | None = None,
    run_id_override: str | None = None,
    tracer: TraceLogger | None = None,
    executor: Executor | None = None,
    prompt: Callable[[str], str] = input,
) -> PipelineResult:
    """Run the workflow from a config file."""

    config = load_config(config_path)
    repo_root = _repo_root(config_path, config)
    mode = str(mode_override or config.get("mode") or "full")
    if mode not in VALID_MODES:
        raise ValueError(f"unsupported pipeline mode: {mode}")

    run_id = str(run_id_override or config.get("run_id") or _new_run_id())
    run_dir = _run_dir(repo_root, config, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    command_executor = executor or _default_executor
    orchestrator = PipelineOrchestrator(
        config=config,
        config_path=Path(config_path),
        repo_root=repo_root,
        mode=mode,
        run_id=run_id,
        run_dir=run_dir,
        non_interactive=_non_interactive(config, non_interactive),
        tracer=tracer,
        executor=command_executor,
        prompt=prompt,
        started_at=started_at,
        started_monotonic=started,
    )
    return orchestrator.run()


class PipelineOrchestrator:
    """Stateful workflow run implementation."""

    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        config_path: Path,
        repo_root: Path,
        mode: str,
        run_id: str,
        run_dir: Path,
        non_interactive: bool,
        tracer: TraceLogger | None,
        executor: Executor,
        prompt: Callable[[str], str],
        started_at: str,
        started_monotonic: float,
    ) -> None:
        self.config = dict(config)
        self.config_path = config_path
        self.repo_root = repo_root
        self.mode = mode
        self.run_id = run_id
        self.run_dir = run_dir
        self.non_interactive = non_interactive
        self.tracer = tracer
        self.executor = executor
        self.prompt = prompt
        self.started_at = started_at
        self.started_monotonic = started_monotonic
        self.state_path = run_dir / STATE_FILE
        self.state = self._load_state()

    def run(self) -> PipelineResult:
        self._trace("workflow", "start", mode=self.mode, run_id=self.run_id)
        performance_findings: Path | None = None
        patches: Path | None = None
        merged_report: Path | None = None
        errors: list[str] = []
        exit_status = "success"

        try:
            if self.mode in {"full", "a-only"}:
                performance_findings = self._run_a()
            else:
                performance_findings = self._external_b_input()

            if self.mode == "full":
                self._run_gate(
                    name="gate_findings_review",
                    title="Gate 1 findings review",
                    artifact=performance_findings,
                    prompt_text=(
                        "Gate 1: approve findings for Skill B patch suggestion "
                        "generation? [Y/n] "
                    ),
                )

            if self.mode in {"full", "b-only"}:
                patches = self._run_b(performance_findings)
                self._run_gate(
                    name="gate_patch_approval",
                    title="Gate 2 patch approval",
                    artifact=patches,
                    prompt_text="Gate 2: approve generated patch review package? [Y/n] ",
                )

            merged_report = self._write_merged_report(
                performance_findings=performance_findings,
                patches=patches,
            )
            self._write_state()
        except Exception as exc:
            exit_status = "failed"
            errors.append(str(exc))
            self._trace("workflow", "failed", level="ERROR", error=str(exc))
            self._write_state()
            run_report = self._write_workflow_run_report(
                performance_findings=performance_findings,
                patches=patches,
                merged_report=None,
                exit_status=exit_status,
                errors=errors,
            )
            raise PipelineError(str(exc)) from exc

        run_report = self._write_workflow_run_report(
            performance_findings=performance_findings,
            patches=patches,
            merged_report=merged_report,
            exit_status=exit_status,
            errors=errors,
        )
        self._trace("workflow", "success", run_report=str(run_report))
        return PipelineResult(
            run_id=self.run_id,
            run_dir=self.run_dir,
            mode=self.mode,
            state_path=self.state_path,
            performance_findings_path=performance_findings,
            patches_path=patches,
            merged_report_path=merged_report,
            run_report_path=run_report,
        )

    def _run_a(self) -> Path:
        a_config = _mapping(self.config.get("a"))
        resumed_capture = self._completed_output("a_capture", "bundle_dir")
        if resumed_capture is not None:
            self._trace("a_capture", "resume", bundle_dir=str(resumed_capture))
            bundle = resumed_capture
        else:
            bundle_dir = a_config.get("bundle_dir")
            if bundle_dir:
                bundle = _resolve_path(bundle_dir, self.repo_root)
                self._record_stage(
                    "a_capture",
                    {
                        "status": "success",
                        "skipped": True,
                        "reason": "pre-captured bundle provided by config",
                        "outputs": {"bundle_dir": str(bundle)},
                    },
                )
            else:
                bundle = self._run_a_capture(a_config)

        resumed_report = self._completed_output("a_report", "performance_findings")
        if resumed_report is not None:
            self._trace("a_report", "resume", performance_findings=str(resumed_report))
            return resumed_report

        analysis_path = self._run_a_analyze(a_config, bundle)
        return self._run_a_report(a_config, analysis_path)

    def _run_a_capture(self, a_config: Mapping[str, Any]) -> Path:
        capture_job = a_config.get("capture_job")
        if not capture_job:
            raise ValueError("A stage requires a.capture_job or a.bundle_dir")
        stage_dir = self._stage_dir("a_capture")
        job_path = _resolve_path(capture_job, self.repo_root)
        cmd = [
            sys.executable,
            "-m",
            "perf_hotspot_analyzer",
            "capture",
            "--job",
            str(job_path),
            "--repo-root",
            str(self.repo_root),
            "--output-dir",
            str(stage_dir),
        ]
        if bool(a_config.get("keep_remote")):
            cmd.append("--keep-remote")
        completed = self._run_command("a_capture", cmd)
        bundle = _capture_bundle_dir(stage_dir, job_path)
        self._record_stage(
            "a_capture",
            {
                "status": "success",
                "command": _command_record(completed),
                "outputs": {"bundle_dir": str(bundle)},
            },
        )
        return bundle

    def _run_a_analyze(self, a_config: Mapping[str, Any], bundle_dir: Path) -> Path:
        resumed = self._completed_output("a_analyze", "analysis_path")
        if resumed is not None:
            self._trace("a_analyze", "resume", analysis_path=str(resumed))
            return resumed
        stage_dir = self._stage_dir("a_analyze")
        analysis_path = stage_dir / "postprocess.json"
        cmd = [
            sys.executable,
            "-m",
            "perf_hotspot_analyzer",
            "analyze",
            "--bundle-dir",
            str(bundle_dir),
            "--repo-root",
            str(self.repo_root),
            "--output",
            str(analysis_path),
            "--output-dir",
            str(stage_dir),
        ]
        ownership = a_config.get("ownership")
        if ownership:
            cmd.extend(["--ownership", str(_resolve_path(ownership, self.repo_root))])
        if a_config.get("top_n") is not None:
            cmd.extend(["--top-n", str(a_config["top_n"])])
        completed = self._run_command("a_analyze", cmd)
        self._record_stage(
            "a_analyze",
            {
                "status": "success",
                "command": _command_record(completed),
                "outputs": {"analysis_path": str(analysis_path)},
            },
        )
        return analysis_path

    def _run_a_report(self, a_config: Mapping[str, Any], analysis_path: Path) -> Path:
        resumed = self._completed_output("a_report", "performance_findings")
        if resumed is not None:
            self._trace("a_report", "resume", performance_findings=str(resumed))
            return resumed
        stage_dir = self._stage_dir("a_report")
        cmd = [
            sys.executable,
            "-m",
            "perf_hotspot_analyzer",
            "report",
            "--analysis",
            str(analysis_path),
            "--repo-root",
            str(self.repo_root),
            "--output-dir",
            str(stage_dir),
        ]
        completed = self._run_command("a_report", cmd)
        findings = stage_dir / "performance-findings.json"
        self._record_stage(
            "a_report",
            {
                "status": "success",
                "command": _command_record(completed),
                "outputs": {
                    "performance_findings": str(findings),
                    "analysis_report": str(stage_dir / "analysis-report.md"),
                },
            },
        )
        return findings

    def _external_b_input(self) -> Path:
        resumed = self._completed_output("b_input", "performance_findings")
        if resumed is not None:
            self._trace("b_input", "resume", performance_findings=str(resumed))
            return resumed
        b_config = _mapping(self.config.get("b"))
        raw_input = b_config.get("input")
        if not raw_input:
            raise ValueError("B-only mode requires b.input")
        path = _resolve_path(raw_input, self.repo_root)
        self._record_stage(
            "b_input",
            {
                "status": "success",
                "outputs": {"performance_findings": str(path)},
            },
        )
        return path

    def _run_b(self, input_report: Path) -> Path:
        resumed = self._completed_output("b_run", "patches")
        if resumed is not None:
            self._trace("b_run", "resume", patches=str(resumed))
            return resumed
        b_config = _mapping(self.config.get("b"))
        stage_dir = self._stage_dir("b_run")
        cmd = [
            sys.executable,
            "-m",
            "perf_suggestion_patch",
            "analyze",
            "--input",
            str(input_report),
            "--format",
            str(b_config.get("format") or "auto"),
            "--repo-root",
            str(_resolve_path(b_config.get("repo_root") or self.repo_root, self.repo_root)),
            "--output-dir",
            str(stage_dir),
        ]
        if b_config.get("baseline_report"):
            cmd.extend(
                ["--baseline-report", str(_resolve_path(b_config["baseline_report"], self.repo_root))]
            )
        if b_config.get("target_name"):
            cmd.extend(["--target-name", str(b_config["target_name"])])
        if b_config.get("renamed_map"):
            cmd.extend(["--renamed-map", json.dumps(b_config["renamed_map"], sort_keys=True)])
        completed = self._run_command("b_run", cmd)
        patches = stage_dir / "patches.json"
        self._record_stage(
            "b_run",
            {
                "status": "success",
                "command": _command_record(completed),
                "outputs": {
                    "patches": str(patches),
                    "patch_report": str(stage_dir / "patch-report.md"),
                },
            },
        )
        return patches

    def _write_merged_report(
        self,
        *,
        performance_findings: Path | None,
        patches: Path | None,
    ) -> Path:
        report_path = self.run_dir / "merged-report.md"
        findings_counts = _artifact_counts(performance_findings, "findings")
        patch_counts = _artifact_counts(patches, "patches")
        gate_records = _gate_decision_records(self.state)
        lines = [
            "# Perf Optimization Pipeline Report",
            "",
            "## Review Status",
            "",
            f"- Mode: `{self.mode}`",
            f"- Run ID: `{self.run_id}`",
            f"- Non-interactive: `{str(self.non_interactive).lower()}`",
            f"- Findings: {findings_counts['total']}",
            f"- Patches: {patch_counts['total']}",
            "",
            "| Gate | Decision | Mode | Counts | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
        if gate_records:
            for gate in gate_records:
                counts = gate.get("counts", {})
                lines.append(
                    "| {gate} | {decision} | {mode} | {counts} | {reason} |".format(
                        gate=gate.get("gate", ""),
                        decision=gate.get("decision", ""),
                        mode=gate.get("mode", ""),
                        counts=json.dumps(counts, sort_keys=True),
                        reason=str(gate.get("reason", "")).replace("|", "\\|"),
                    )
                )
        else:
            lines.append("| none | n/a | n/a | {} | no workflow gate in this mode |")

        lines.extend(
            [
                "",
                "## Pending Review Decisions",
                "",
            ]
        )
        if patch_counts["total"]:
            lines.append("- Review each generated patch before applying anything outside this run directory.")
            lines.append("- The workflow did not apply, commit, or push generated patches.")
        elif self.mode == "a-only":
            lines.append("- Review findings; no Skill B patch suggestions were requested in A-only mode.")
        else:
            lines.append("- No patches were generated.")

        analysis_report = self._stage_output_path("a_report", "analysis_report")
        patch_report = self._stage_output_path("b_run", "patch_report")
        lines.extend(
            [
                "",
                "## Artifacts",
                "",
                f"- State: `{self.state_path}`",
                f"- Performance findings: `{performance_findings or ''}`",
                f"- Suggestion patches: `{patches or ''}`",
                "",
                "## Analyzer Report",
                "",
            ]
        )
        lines.append(_read_report_body(analysis_report, "Analyzer report is not available for this mode."))
        lines.extend(["", "## Patch Report", ""])
        lines.append(_read_report_body(patch_report, "Patch report is not available for this mode."))
        report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self._record_stage(
            "merged_report",
            {
                "status": "success",
                "outputs": {"merged_report": str(report_path)},
            },
        )
        return report_path

    def _stage_output_path(self, stage: str, output_key: str) -> Path | None:
        stage_record = _mapping(_mapping(self.state.get("stages")).get(stage))
        raw_path = _mapping(stage_record.get("outputs")).get(output_key)
        if not raw_path:
            return None
        path = Path(str(raw_path))
        return path if path.exists() else None

    def _run_gate(
        self,
        *,
        name: str,
        title: str,
        artifact: Path,
        prompt_text: str,
    ) -> None:
        existing = _mapping(_mapping(self.state.get("gates")).get(name))
        if existing.get("status") == "pass":
            self._trace(name, "resume", mode=existing.get("mode", "unknown"))
            return
        gates_config = _mapping(self.config.get("gates"))
        if gates_config.get(name) is False:
            decision = "pass"
            reason = "gate disabled by config"
            mode = "disabled"
        elif self.non_interactive:
            decision = "pass"
            reason = "non-interactive auto pass; no apply/commit/push performed"
            mode = "non-interactive"
        else:
            answer = self.prompt(prompt_text).strip().lower()
            decision = "pass" if answer in {"", "y", "yes"} else "rejected"
            reason = "interactive approval" if decision == "pass" else "interactive rejection"
            mode = "interactive"

        record = {
            "status": decision,
            "title": title,
            "mode": mode,
            "reason": reason,
            "artifact": str(artifact),
            "counts": _gate_counts(artifact),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.state.setdefault("gates", {})[name] = record
        self._write_state()
        self._trace(name, decision, mode=mode, artifact=str(artifact), reason=reason)
        if decision != "pass":
            raise PipelineError(f"{title} rejected: {reason}")

    def _completed_output(self, stage: str, output_key: str) -> Path | None:
        stage_record = _mapping(_mapping(self.state.get("stages")).get(stage))
        if stage_record.get("status") != "success":
            return None
        outputs = _mapping(stage_record.get("outputs"))
        raw_path = outputs.get(output_key)
        if not raw_path:
            return None
        path = Path(str(raw_path))
        if path.exists():
            return path
        return None

    def _run_command(self, stage: str, cmd: list[str]) -> CommandResult:
        timeout_s = _command_timeout(self.config)
        self._trace(stage, "command_start", argv=cmd, timeout_s=timeout_s)
        completed = self.executor(cmd, timeout_s)
        level = "INFO" if completed.returncode == 0 else "ERROR"
        self._trace(
            stage,
            "command_finish",
            level=level,
            returncode=completed.returncode,
            elapsed_ms=completed.elapsed_ms,
        )
        if completed.returncode != 0:
            self._record_stage(
                stage,
                {
                    "status": "failed",
                    "command": _command_record(completed),
                },
            )
            raise PipelineError(
                f"{stage} failed with exit code {completed.returncode}: {completed.stderr}"
            )
        return completed

    def _stage_dir(self, name: str) -> Path:
        path = self.run_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _record_stage(self, name: str, data: Mapping[str, Any]) -> None:
        stages = self.state.setdefault("stages", {})
        stages[name] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **dict(data),
        }
        self._write_state()

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {
            "schema_version": "workflow-state/v1",
            "run_id": self.run_id,
            "mode": self.mode,
            "config_path": str(self.config_path),
            "run_dir": str(self.run_dir),
            "stages": {},
            "gates": {},
        }

    def _write_state(self) -> None:
        self.state_path.write_text(
            json.dumps(self.state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _write_workflow_run_report(
        self,
        *,
        performance_findings: Path | None,
        patches: Path | None,
        merged_report: Path | None,
        exit_status: str,
        errors: Sequence[str],
    ) -> Path:
        report_path = self.run_dir / "run-report.json"
        report = {
            "schema_version": "run-report/v1",
            "trace_id": self.tracer.trace_id if self.tracer is not None else self.run_id,
            "skill": "perf-optimization-pipeline",
            "started_at": self.started_at,
            "total_ms": int((time.monotonic() - self.started_monotonic) * 1000),
            "by_step": _stage_elapsed(self.state),
            "input": {
                "mode": self.mode,
                "config_path": str(self.config_path),
                "non_interactive": self.non_interactive,
            },
            "findings": _artifact_counts(performance_findings, "findings"),
            "anchors": {"resolved": 0, "confidence_distribution": {}},
            "gate_decisions": _gate_decision_records(self.state),
            "patches": _artifact_counts(patches, "patches"),
            "degradations": [],
            "artifacts": {
                "run_dir": str(self.run_dir),
                "performance_findings": str(performance_findings) if performance_findings else "",
                "patches": str(patches) if patches else "",
                "merged_report": str(merged_report) if merged_report else "",
                "state": str(self.state_path),
            },
            "exit_status": exit_status,
            "errors": list(errors),
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report_path

    def _trace(self, step: str, event: str, level: str = "INFO", **fields: Any) -> None:
        if self.tracer is not None:
            self.tracer.event(step, event, level, **fields)


def _default_executor(argv: Sequence[str], timeout_s: int) -> CommandResult:
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(argv),
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_s,
        )
        return CommandResult(
            args=list(argv),
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            args=list(argv),
            returncode=124,
            stdout=_decode_timeout_stream(exc.stdout),
            stderr=_decode_timeout_stream(exc.stderr) or "command timed out",
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )


def _repo_root(config_path: str | Path, config: Mapping[str, Any]) -> Path:
    configured = config.get("repo_root")
    if configured:
        return _resolve_path(configured, Path(config_path).resolve().parent)
    return Path(config_path).resolve().parent


def _run_dir(repo_root: Path, config: Mapping[str, Any], run_id: str) -> Path:
    output_dir = Path(str(config.get("output_dir") or ".perf-skill/runs")).expanduser()
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    return output_dir / run_id


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _non_interactive(config: Mapping[str, Any], override: bool | None) -> bool:
    if override is not None:
        return override
    return bool(config.get("non_interactive", False))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _resolve_path(value: object, base: Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return base / path


def _capture_bundle_dir(stage_dir: Path, job_path: Path) -> Path:
    try:
        job = load_yaml(job_path)
        output = _mapping(job.get("output"))
        bundle_name = str(output.get("bundle_name") or "")
        if bundle_name:
            for suffix in (".tar.gz", ".tgz", ".zip"):
                if bundle_name.endswith(suffix):
                    bundle_name = bundle_name[: -len(suffix)]
                    break
            return stage_dir / bundle_name
    except Exception:
        pass
    manifests = sorted(stage_dir.glob("*/manifest.json"))
    if len(manifests) == 1:
        return manifests[0].parent
    raise PipelineError(f"cannot determine capture bundle directory under {stage_dir}")


def _command_timeout(config: Mapping[str, Any]) -> int:
    timeouts = _mapping(config.get("timeouts"))
    return int(timeouts.get("command_s") or config.get("command_timeout_s") or 300)


def _command_record(completed: CommandResult) -> dict[str, Any]:
    return {
        "args": completed.args,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "elapsed_ms": completed.elapsed_ms,
    }


def _stage_elapsed(state: Mapping[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for name, stage in _mapping(state.get("stages")).items():
        command = stage.get("command") if isinstance(stage, Mapping) else None
        if isinstance(command, Mapping):
            result[str(name)] = int(command.get("elapsed_ms") or 0)
        else:
            result[str(name)] = 0
    return result


def _artifact_counts(path: Path | None, key: str) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"total": 0, "by_kind": {}}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"total": 0, "by_kind": {}}
    items = document.get(key, [])
    if not isinstance(items, list):
        return {"total": 0, "by_kind": {}}
    by_kind: dict[str, int] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("kind") or item.get("status") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {"total": len(items), "by_kind": by_kind}


def _gate_counts(path: Path) -> dict[str, Any]:
    if path.name == "patches.json":
        return _artifact_counts(path, "patches")
    return _artifact_counts(path, "findings")


def _gate_decision_records(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    gates = _mapping(state.get("gates"))
    for name, gate in sorted(gates.items()):
        if not isinstance(gate, Mapping):
            continue
        records.append(
            {
                "gate": str(name),
                "decision": gate.get("status", "unknown"),
                "mode": gate.get("mode", "unknown"),
                "reason": gate.get("reason", ""),
                "artifact": gate.get("artifact", ""),
                "counts": gate.get("counts", {}),
            }
        )
    return records


def _read_report_body(path: Path | None, fallback: str) -> str:
    if path is None:
        return fallback
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return fallback


def _decode_timeout_stream(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
