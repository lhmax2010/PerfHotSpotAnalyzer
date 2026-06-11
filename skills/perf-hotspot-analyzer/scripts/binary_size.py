"""Binary size analysis for ELF section findings."""

from __future__ import annotations

import fnmatch
import json
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from common import schema_validate
from common.schema_validate import PERFORMANCE_FINDINGS
from common.simple_yaml import load_yaml


READ_TIMEOUT_S = 20
ABSOLUTE_THRESHOLD_BYTES = 64 * 1024
SECTION_RATIO_THRESHOLD = 0.10
TOP_N = 5
REGRESSION_ABS_THRESHOLD_BYTES = 1024
REGRESSION_PCT_THRESHOLD = 5.0


@dataclass(frozen=True)
class Section:
    index: int
    name: str
    section_type: str
    address: int
    offset: int
    size: int
    entry_size: int
    flags: str
    align: int

    @property
    def is_alloc(self) -> bool:
        return "A" in self.flags


@dataclass(frozen=True)
class OwnershipProfile:
    owned_paths: tuple[str, ...] = ()
    third_party_paths: tuple[str, ...] = ()
    system_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class OwnershipDecision:
    ownership: str
    reason: str


@dataclass(frozen=True)
class Threshold:
    type: str
    value: float
    unit: str
    reason: str


def read_elf_sections(elf_path: str | Path, *, readelf: str = "readelf") -> list[Section]:
    path = Path(elf_path)
    result = subprocess.run(
        [readelf, "-S", "--wide", str(path)],
        check=False,
        text=True,
        capture_output=True,
        timeout=READ_TIMEOUT_S,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"readelf failed for {path}: {detail}")
    sections = parse_readelf_sections(result.stdout)
    if not sections:
        raise ValueError(f"readelf returned no parseable sections for {path}")
    return sections


def parse_readelf_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    for raw in text.splitlines():
        parsed = parse_readelf_section_line(raw)
        if parsed is not None:
            sections.append(parsed)
    return sections


def parse_readelf_section_line(line: str) -> Section | None:
    if not line.lstrip().startswith("["):
        return None
    match = re.match(
        r"^\s*\[\s*(?P<index>\d+)\]\s+"
        r"(?P<name>\S+)\s+"
        r"(?P<type>\S+)\s+"
        r"(?P<address>[0-9A-Fa-f]+)\s+"
        r"(?P<offset>[0-9A-Fa-f]+)\s+"
        r"(?P<size>[0-9A-Fa-f]+)\s+"
        r"(?P<entry_size>[0-9A-Fa-f]+)\s+"
        r"(?P<flags>\S*)\s+"
        r"(?P<link>\d+)\s+"
        r"(?P<info>\d+)\s+"
        r"(?P<align>\d+)",
        line,
    )
    if match is None:
        return None
    return Section(
        index=int(match.group("index")),
        name=match.group("name"),
        section_type=match.group("type"),
        address=int(match.group("address"), 16),
        offset=int(match.group("offset"), 16),
        size=int(match.group("size"), 16),
        entry_size=int(match.group("entry_size"), 16),
        flags=match.group("flags"),
        align=int(match.group("align")),
    )


def alloc_sections(sections: Iterable[Section]) -> list[Section]:
    return [section for section in sections if section.is_alloc and section.size > 0]


def total_alloc_size(sections: Iterable[Section]) -> int:
    return sum(section.size for section in alloc_sections(sections))


def section_map(sections: Sequence[Section]) -> dict[str, Section]:
    return {section.name: section for section in sections}


def load_ownership_profile(path: str | Path | None) -> OwnershipProfile:
    if path is None or not Path(path).exists():
        return OwnershipProfile()
    raw = load_yaml(path)
    return OwnershipProfile(
        owned_paths=tuple(str(item) for item in raw.get("owned_paths", [])),
        third_party_paths=tuple(str(item) for item in raw.get("third_party_paths", [])),
        system_paths=tuple(str(item) for item in raw.get("system_paths", [])),
    )


def classify_elf_path(
    elf_path: str | Path,
    profile: OwnershipProfile,
) -> OwnershipDecision:
    path = str(Path(elf_path))
    owned_rule = _first_match(path, profile.owned_paths)
    if owned_rule is not None:
        return OwnershipDecision("owned", f"owned_paths:{owned_rule}")
    third_party_rule = _first_match(path, profile.third_party_paths)
    if third_party_rule is not None:
        return OwnershipDecision("third-party", f"third_party_paths:{third_party_rule}")
    system_rule = _first_match(path, profile.system_paths)
    if system_rule is not None:
        return OwnershipDecision("system", f"system_paths:{system_rule}")
    return OwnershipDecision("unknown", "no matching ownership rule")


def build_binary_size_document(
    *,
    elf_path: str | Path,
    baseline_path: str | Path | None = None,
    repo_root: str | Path = ".",
    ownership_path: str | Path | None = None,
    user_budget_bytes: int | None = None,
    readelf: str = "readelf",
) -> dict[str, Any]:
    sections = read_elf_sections(elf_path, readelf=readelf)
    profile = load_ownership_profile(ownership_path)
    ownership = classify_elf_path(elf_path, profile)
    source_report = {
        "id": "binary-size-current" if baseline_path is not None else "binary-size",
        "path": str(elf_path),
        "source_format": "external",
        "parser": "readelf-section-table",
        "confidence": 0.95,
    }
    source_reports = [source_report]
    comparison: dict[str, Any] | None = None
    if baseline_path is None:
        findings = build_large_findings(
            sections=sections,
            elf_path=Path(elf_path),
            source_id=source_report["id"],
            ownership=ownership,
            user_budget_bytes=user_budget_bytes,
        )
    else:
        baseline_sections = read_elf_sections(baseline_path, readelf=readelf)
        source_reports.append(
            {
                "id": "binary-size-baseline",
                "path": str(baseline_path),
                "source_format": "external",
                "parser": "readelf-section-table",
                "confidence": 0.95,
            }
        )
        comparison = {
            "current_report": str(elf_path),
            "baseline_report": str(baseline_path),
            "compare_method": "name-match",
            "renamed_map": {},
        }
        findings = build_regression_findings(
            current_sections=sections,
            baseline_sections=baseline_sections,
            current_path=Path(elf_path),
            baseline_path=Path(baseline_path),
            source_id=source_report["id"],
            ownership=ownership,
        )
    document = {
        "schema_version": "1.0",
        "report_types": ["binary-size"],
        "target": {
            "name": Path(elf_path).name,
            "kind": "binary",
            "repo_root": str(Path(repo_root)),
            "platform": {"os": "linux", "arch": _normalized_arch()},
        },
        "source_reports": source_reports,
        "run_context": {
            "device": "host",
            "cpu_governor": "unknown",
            "core_count": os.cpu_count() or 1,
            "repeat_count": 1,
            "warmup_count": 0,
        },
        "findings": findings,
        "summary_metrics": {
            "alloc_section_bytes": total_alloc_size(sections),
            "alloc_section_count": len(alloc_sections(sections)),
        },
        "provenance": {
            "generated_by": "perf-hotspot-analyzer/binary_size",
            "version": "1.0.0",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }
    if comparison is not None:
        document["comparison"] = comparison
    schema_validate.validate_document(document, document_type=PERFORMANCE_FINDINGS)
    return document


def build_large_findings(
    *,
    sections: Sequence[Section],
    elf_path: Path,
    source_id: str,
    ownership: OwnershipDecision,
    user_budget_bytes: int | None = None,
) -> list[dict[str, Any]]:
    alloc = sorted(alloc_sections(sections), key=lambda item: (-item.size, item.name))
    total = max(1, sum(section.size for section in alloc))
    findings: list[dict[str, Any]] = []
    for rank, section in enumerate(alloc, start=1):
        threshold = choose_large_threshold(
            section=section,
            rank=rank,
            total_alloc_bytes=total,
            user_budget_bytes=user_budget_bytes,
        )
        if threshold is None:
            continue
        default_actionability = (
            "informational" if threshold.type == "top-n" else "actionable"
        )
        actionability, actionability_reason = apply_binary_actionability(
            default_actionability,
            ownership=ownership,
            threshold=threshold,
        )
        findings.append(
            {
                "id": f"F{len(findings) + 1:03d}",
                "kind": "binary-size-large",
                "title": _large_title(section, threshold),
                "source_ref": {
                    "source_id": source_id,
                    "locator": f"$.sections['{section.name}']",
                    "label": section.name,
                },
                "ownership": ownership.ownership,
                "actionability": actionability,
                "evidence": {
                    "metric": "section_bytes",
                    "value": section.size,
                    "unit": "bytes",
                    "rank": rank,
                    "section": section.name,
                    "file": str(elf_path),
                    "threshold": {
                        "type": threshold.type,
                        "value": threshold.value,
                        "unit": threshold.unit,
                        "reason": threshold.reason,
                    },
                    "ownership_reason": ownership.reason,
                    "actionability_reason": actionability_reason,
                },
                "confidence": 0.9,
            }
        )
    return findings


def build_regression_findings(
    *,
    current_sections: Sequence[Section],
    baseline_sections: Sequence[Section],
    current_path: Path,
    baseline_path: Path,
    source_id: str,
    ownership: OwnershipDecision,
) -> list[dict[str, Any]]:
    current = {section.name: section for section in alloc_sections(current_sections)}
    baseline = {section.name: section for section in alloc_sections(baseline_sections)}
    candidates: list[tuple[str, int, int, int, float, str]] = []
    for name in sorted(set(current) | set(baseline)):
        current_size = current.get(name).size if name in current else 0
        baseline_size = baseline.get(name).size if name in baseline else 0
        if current_size == baseline_size:
            continue
        delta_abs = abs(current_size - baseline_size)
        delta_pct = _delta_pct(current_size, baseline_size)
        if delta_abs < REGRESSION_ABS_THRESHOLD_BYTES and delta_pct < REGRESSION_PCT_THRESHOLD:
            continue
        direction = "increase" if current_size >= baseline_size else "decrease"
        candidates.append((name, current_size, baseline_size, delta_abs, delta_pct, direction))

    findings: list[dict[str, Any]] = []
    for name, current_size, baseline_size, delta_abs, delta_pct, direction in sorted(
        candidates,
        key=lambda item: (-item[3], item[0]),
    ):
        default_actionability = "actionable"
        actionability, actionability_reason = apply_binary_actionability(
            default_actionability,
            ownership=ownership,
            threshold=Threshold(
                "binary-size-regression",
                REGRESSION_PCT_THRESHOLD,
                "percent",
                "section changed by at least 5% or 1KB",
            ),
        )
        findings.append(
            {
                "id": f"F{len(findings) + 1:03d}",
                "kind": "binary-size-regression",
                "title": f"{name} {direction}d by {delta_abs} bytes",
                "source_ref": {
                    "source_id": source_id,
                    "locator": f"$.sections['{name}']",
                    "label": name,
                },
                "ownership": ownership.ownership,
                "actionability": actionability,
                "evidence": {
                    "metric": "section_bytes",
                    "value": current_size,
                    "unit": "bytes",
                    "section": name,
                    "file": str(current_path),
                    "baseline": {
                        "value": baseline_size,
                        "label": baseline_path.name,
                    },
                    "delta": {
                        "abs": delta_abs,
                        "pct": round(delta_pct, 2),
                        "direction": direction,
                    },
                    "ownership_reason": ownership.reason,
                    "actionability_reason": actionability_reason,
                },
                "confidence": 0.9,
            }
        )
    return findings


def choose_large_threshold(
    *,
    section: Section,
    rank: int,
    total_alloc_bytes: int,
    user_budget_bytes: int | None = None,
) -> Threshold | None:
    if user_budget_bytes is not None and section.size >= user_budget_bytes:
        return Threshold(
            "user-budget",
            user_budget_bytes,
            "bytes",
            f"section exceeds user budget of {user_budget_bytes} bytes",
        )
    if section.size >= ABSOLUTE_THRESHOLD_BYTES:
        return Threshold(
            "absolute-bytes",
            ABSOLUTE_THRESHOLD_BYTES,
            "bytes",
            "section exceeds 64KB",
        )
    ratio = section.size / max(1, total_alloc_bytes)
    if ratio >= SECTION_RATIO_THRESHOLD:
        return Threshold(
            "section-ratio",
            SECTION_RATIO_THRESHOLD,
            "ratio",
            "section is at least 10% of allocated bytes",
        )
    if rank <= TOP_N:
        return Threshold(
            "top-n",
            TOP_N,
            "rank",
            "top 5 largest allocated sections",
        )
    return None


def apply_binary_actionability(
    default_actionability: str,
    *,
    ownership: OwnershipDecision,
    threshold: Threshold,
) -> tuple[str, str]:
    if default_actionability != "actionable":
        return default_actionability, f"{threshold.type} is advisory by default"
    if ownership.ownership == "owned":
        return "actionable", f"{threshold.type} threshold on owned binary"
    return (
        "informational",
        f"{threshold.type} threshold hit but ownership={ownership.ownership} has no attribution anchor",
    )


def write_binary_size_outputs(
    *,
    document: Mapping[str, Any],
    output_dir: str | Path,
    trace_id: str,
    started_at: str,
    total_ms: int,
    exit_status: str = "success",
    errors: Sequence[str] = (),
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "performance-findings.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "analysis-report.md").write_text(
        render_binary_size_markdown(document),
        encoding="utf-8",
    )
    (output / "run-report.json").write_text(
        json.dumps(
            build_binary_size_run_report(
                document=document,
                trace_id=trace_id,
                started_at=started_at,
                total_ms=total_ms,
                exit_status=exit_status,
                errors=errors,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def render_binary_size_markdown(document: Mapping[str, Any]) -> str:
    lines = [
        "# Binary Size Analysis",
        "",
        "| Kind | Section | Bytes | Threshold | Actionability |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for finding in document.get("findings", []):
        evidence = finding["evidence"]
        threshold = evidence.get("threshold", {})
        lines.append(
            "| {kind} | `{section}` | {value} | {threshold} | {actionability} |".format(
                kind=finding["kind"],
                section=evidence.get("section", ""),
                value=int(evidence.get("value", 0)),
                threshold=threshold.get("type", "n/a"),
                actionability=finding.get("actionability", "informational"),
            )
        )
    lines.extend(["", "## Diagnosis", "", "pending", ""])
    return "\n".join(lines)


def build_binary_size_run_report(
    *,
    document: Mapping[str, Any],
    trace_id: str,
    started_at: str,
    total_ms: int,
    exit_status: str,
    errors: Sequence[str] = (),
) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    for finding in document.get("findings", []):
        by_kind[finding["kind"]] = by_kind.get(finding["kind"], 0) + 1
    return {
        "schema_version": "run-report/v1",
        "trace_id": trace_id,
        "skill": "perf-hotspot-analyzer",
        "started_at": started_at,
        "total_ms": total_ms,
        "by_step": {"binary-size": total_ms},
        "input": {"source_formats": ["external"]},
        "findings": {"total": len(document.get("findings", [])), "by_kind": by_kind},
        "anchors": {"resolved": 0, "confidence_distribution": {}},
        "gate_decisions": [
            {
                "finding": finding["id"],
                "decision": finding.get("actionability", "informational"),
                "reason": finding.get("evidence", {}).get("actionability_reason", ""),
            }
            for finding in document.get("findings", [])
        ],
        "patches": {"diff-ready": 0, "needs-review": 0, "advisory-only": 0},
        "degradations": [],
        "exit_status": exit_status,
        "errors": list(errors),
    }


def _first_match(value: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        if fnmatch.fnmatch(value, pattern):
            return pattern
    return None


def _large_title(section: Section, threshold: Threshold) -> str:
    if threshold.type == "top-n":
        return f"{section.name} is in the top 5 allocated sections"
    if threshold.type == "section-ratio":
        return f"{section.name} is at least 10% of allocated bytes"
    if threshold.type == "user-budget":
        return f"{section.name} exceeds the user binary-size budget"
    return f"{section.name} exceeds 64KB"


def _delta_pct(current_size: int, baseline_size: int) -> float:
    if baseline_size == 0:
        return 100.0 if current_size != 0 else 0.0
    return abs(current_size - baseline_size) * 100.0 / baseline_size


def _normalized_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "aarch64"
    if machine.startswith("arm"):
        return "armv7"
    return "x86_64"
