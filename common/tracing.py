"""Small structured tracing helper shared by M0 CLI skeletons."""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
SENSITIVE_KEY_PARTS = ("token", "secret", "password", "credential")


class TraceLogger:
    """Write human-readable console logs and JSONL trace records."""

    def __init__(
        self,
        *,
        skill: str,
        output_dir: str | Path,
        verbose: bool = False,
        trace_id: str | None = None,
    ) -> None:
        self.skill = skill
        self.trace_id = trace_id or uuid.uuid4().hex[:12]
        env_level = os.environ.get("PERF_SKILL_LOG_LEVEL", "").upper()
        self.level_name = "DEBUG" if verbose else env_level or "INFO"
        if self.level_name not in LEVELS:
            self.level_name = "INFO"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.output_dir / f"run-{self.trace_id}.jsonl"
        self._handle: TextIO = self.path.open("a", encoding="utf-8")

    def close(self) -> None:
        self._handle.close()

    def event(self, step: str, event: str, level: str = "INFO", **fields: Any) -> None:
        level_name = level.upper()
        if LEVELS.get(level_name, 20) < LEVELS[self.level_name]:
            return
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "level": level_name,
            "trace_id": self.trace_id,
            "skill": self.skill,
            "step": step,
            "event": event,
        }
        record.update(_sanitize(fields))
        self._handle.write(json.dumps(record, sort_keys=True) + "\n")
        self._handle.flush()
        print(
            f"[{level_name}] trace_id={self.trace_id} step={step} event={event}",
            file=sys.stderr,
        )

    def debug(self, step: str, event: str, **fields: Any) -> None:
        self.event(step, event, "DEBUG", **fields)

    def info(self, step: str, event: str, **fields: Any) -> None:
        self.event(step, event, "INFO", **fields)

    def warn(self, step: str, event: str, **fields: Any) -> None:
        self.event(step, event, "WARN", **fields)

    def error(self, step: str, event: str, **fields: Any) -> None:
        self.event(step, event, "ERROR", **fields)


def start_trace(
    *,
    skill: str,
    output_dir: str | Path,
    verbose: bool = False,
    trace_id: str | None = None,
) -> TraceLogger:
    return TraceLogger(
        skill=skill,
        output_dir=output_dir,
        verbose=verbose,
        trace_id=trace_id,
    )


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, nested in value.items():
            if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS):
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = _sanitize(nested)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value
