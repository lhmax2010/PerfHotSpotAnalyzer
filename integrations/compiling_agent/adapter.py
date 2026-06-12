"""CLI-based Compiling Agent adapter draft.

The real Compiling Agent registration API is not available in v1, so this module
only provides a small subprocess wrapper that a future integration can call.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


DEFAULT_TIMEOUT_S = 300


@dataclass(frozen=True)
class PerfSkillCLIAdapter:
    """Adapter that calls the v1 CLI contract and returns degraded results."""

    repo_root: Path
    python_executable: str = sys.executable
    default_timeout_s: int = DEFAULT_TIMEOUT_S

    def analyze(
        self,
        *,
        config_path: str | Path,
        mode: str | None = None,
        non_interactive: bool = True,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Run the workflow CLI and return a structured result."""

        argv = [
            self.python_executable,
            "-m",
            "perf_optimization_pipeline",
            "pipeline",
            "run",
            "--config",
            str(config_path),
        ]
        if mode:
            argv.extend(["--mode", mode])
        if non_interactive:
            argv.append("--non-interactive")
        return self._run_cli(argv, timeout_s=timeout_s)

    def apply(
        self,
        *,
        patches_path: str | Path,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Return review-only status; v1 never applies generated patches."""

        _ = timeout_s
        return {
            "status": "degraded",
            "exit_code": 0,
            "degraded_reason": (
                "v1 adapter is review-only; generated patches must be applied "
                "manually after human approval"
            ),
            "artifacts": {"patches": str(patches_path)},
            "stdout": "",
            "stderr": "",
            "command": [],
        }

    def _run_cli(
        self,
        argv: Sequence[str],
        *,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        timeout = int(timeout_s or self.default_timeout_s)
        try:
            completed = subprocess.run(
                list(argv),
                cwd=self.repo_root,
                check=False,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "degraded",
                "exit_code": 124,
                "degraded_reason": f"timeout after {timeout}s",
                "artifacts": {},
                "stdout": _decode_stream(exc.stdout),
                "stderr": _decode_stream(exc.stderr),
                "command": list(argv),
            }
        except OSError as exc:
            return {
                "status": "degraded",
                "exit_code": 3,
                "degraded_reason": str(exc),
                "artifacts": {},
                "stdout": "",
                "stderr": str(exc),
                "command": list(argv),
            }

        artifacts = _artifacts_from_stdout(completed.stdout)
        if completed.returncode == 0:
            return {
                "status": "success",
                "exit_code": 0,
                "degraded_reason": "",
                "artifacts": artifacts,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "command": list(argv),
            }
        return {
            "status": "degraded",
            "exit_code": completed.returncode,
            "degraded_reason": f"cli exited with {completed.returncode}",
            "artifacts": artifacts,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "command": list(argv),
        }


def _artifacts_from_stdout(stdout: str) -> dict[str, str]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    artifacts: dict[str, str] = {}
    if lines:
        artifacts["run_dir"] = lines[0]
    if len(lines) >= 2:
        artifacts["run_report"] = lines[1]
    if len(lines) >= 3:
        artifacts["merged_report"] = lines[2]
    return artifacts


def _decode_stream(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
