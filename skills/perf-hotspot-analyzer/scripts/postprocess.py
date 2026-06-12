"""Post-process Capture Bundles into deterministic hotspot analysis."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from common.schema_validate import CAPTURE_BUNDLE, validate_document
from common.simple_yaml import load_yaml
from common.tracing import TraceLogger, start_trace


SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh"}
DEFAULT_OWNERSHIP = {
    "owned_build_id_sources": [],
    "owned_paths": [],
    "third_party_paths": [
        "/usr/lib/libgst*.so*",
        "/usr/lib/libgstreamer-*.so*",
        "/usr/lib/libglib-2.0.so*",
        "/usr/lib/libgobject-2.0.so*",
        "/usr/lib/libgio-2.0.so*",
        "/usr/lib/libgthread-2.0.so*",
        "/usr/lib/libdbus-*.so*",
        "/usr/lib64/libgst*.so*",
        "/usr/lib64/libg*.so*",
        "/lib/lib*.so*",
        "/lib64/lib*.so*",
    ],
    "system_paths": [
        "/usr/lib/libc-*.so*",
        "/usr/lib/libpthread-*.so*",
        "/usr/lib/ld-*.so*",
        "/usr/lib64/libc-*.so*",
        "/usr/lib64/libpthread-*.so*",
        "/usr/lib64/ld-*.so*",
        "/lib*/libc-*.so*",
        "/lib*/ld-*.so*",
        "[kernel.kallsyms]",
    ],
    "attribution_strategy": "nearest-to-hotspot",
}


@dataclass
class Frame:
    symbol: str
    dso: str
    ip: str = ""
    file: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    build_id: str | None = None
    ownership: str = "unknown"
    ownership_reason: str = "no-rule"


@dataclass
class StackSample:
    frames: list[Frame]


@dataclass
class Hotspot:
    rank: int
    samples: int
    self_cpu_pct: float
    hot_frame: Frame
    representative_stack: list[Frame]
    callers: list[str]
    actionability: str
    actionability_reason: str
    code_anchor: dict[str, Any] | None = None
    attribution_anchor: dict[str, Any] | None = None
    bottleneck_class: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OwnershipDecision:
    dso: str
    build_id: str | None
    ownership: str
    reason: str


@dataclass(frozen=True)
class OwnershipProfile:
    owned_build_id_sources: list[str]
    owned_paths: list[str]
    third_party_paths: list[str]
    system_paths: list[str]
    attribution_strategy: str = "nearest-to-hotspot"


def postprocess_bundle(
    *,
    bundle_dir: str | Path,
    output: str | Path | None = None,
    repo_root: str | Path = ".",
    ownership_path: str | Path | None = None,
    top_n: int = 10,
    tracer: TraceLogger | None = None,
) -> dict[str, Any]:
    bundle = Path(bundle_dir)
    manifest = _load_json(bundle / "manifest.json")
    validate_document(manifest, document_type=CAPTURE_BUNDLE)
    profile = load_ownership_profile(
        ownership_path or Path(repo_root) / ".perf-skill" / "ownership.yaml"
    )
    dso_build_ids = parse_dso_build_ids(bundle / manifest["artifacts"]["dso_list"])
    perf_script = bundle / manifest["artifacts"]["perf_script"]
    samples = parse_perf_script(perf_script)
    tizen = build_tizen_context(
        manifest=manifest,
        bundle_dir=bundle,
        repo_root=Path(repo_root),
        samples=samples,
        dso_build_ids=dso_build_ids,
    )
    classified_samples, decisions = classify_samples(samples, profile, dso_build_ids)
    hotspots = analyze_hotspots(
        classified_samples,
        profile=profile,
        repo_root=Path(repo_root),
        total_samples=max(1, len(classified_samples)),
        top_n=top_n,
        tracer=tracer,
    )
    document = build_postprocess_document(
        bundle_dir=bundle,
        manifest=manifest,
        hotspots=hotspots,
        ownership_decisions=decisions,
        total_samples=len(classified_samples),
        tizen=tizen,
    )
    if output is not None:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def load_ownership_profile(path: str | Path) -> OwnershipProfile:
    profile_path = Path(path)
    raw = dict(DEFAULT_OWNERSHIP)
    if profile_path.exists():
        loaded = load_yaml(profile_path)
        raw.update(loaded)
    return OwnershipProfile(
        owned_build_id_sources=[str(item) for item in raw.get("owned_build_id_sources", [])],
        owned_paths=[str(item) for item in raw.get("owned_paths", [])],
        third_party_paths=[str(item) for item in raw.get("third_party_paths", [])],
        system_paths=[str(item) for item in raw.get("system_paths", [])],
        attribution_strategy=str(raw.get("attribution_strategy") or "nearest-to-hotspot"),
    )


def parse_perf_script(path: str | Path) -> list[StackSample]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    samples: list[StackSample] = []
    current: list[Frame] = []
    for raw in text.splitlines():
        if not raw.strip():
            _finish_sample(samples, current)
            current = []
            continue
        frame = parse_frame_line(raw)
        if frame is None:
            continue
        is_header = _is_perf_script_header(raw)
        if is_header and current:
            _finish_sample(samples, current)
            current = []
        current.append(frame)
    _finish_sample(samples, current)
    return samples


def parse_frame_line(line: str) -> Frame | None:
    text = line.strip()
    if re.match(r"^[^\s]+\s+\d+/\d+.*:", text):
        text = text.split(":", 1)[1].strip()
    match = re.search(
        r"(?P<ip>(?:0x)?[0-9a-fA-F]+)\s+"
        r"(?P<symbol>[^\s(]+)"
        r"(?:\s+\((?P<dso_paren>[^)]+)\)|\s+(?P<dso>\S+))",
        text,
    )
    if match is None:
        return None
    symbol = _normalize_symbol(match.group("symbol"))
    dso = match.group("dso_paren") or match.group("dso") or ""
    file_name, line_number = _split_srcline(dso)
    if file_name is not None:
        dso = ""
    return Frame(
        symbol=symbol,
        dso=dso,
        ip=match.group("ip"),
        file=file_name,
        line_start=line_number,
        line_end=line_number,
    )


def _is_perf_script_header(line: str) -> bool:
    return bool(re.match(r"^[^\s]+\s+\d+/\d+.*:", line.strip()))


def parse_dso_build_ids(path: str | Path) -> dict[str, str]:
    dso_path = Path(path)
    if not dso_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in dso_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            result[parts[-1]] = parts[0]
    return result


def build_tizen_context(
    *,
    manifest: dict[str, Any],
    bundle_dir: Path,
    repo_root: Path,
    samples: Sequence[StackSample],
    dso_build_ids: dict[str, str],
) -> dict[str, Any] | None:
    device = manifest.get("device", {})
    arch = device.get("arch") if isinstance(device, dict) else None
    if arch not in {"armv7", "aarch64"} and manifest.get("backend") not in {"ssh", "sdb"}:
        return None
    debuginfo_roots = [
        resolve_host_path(root, repo_root)
        for root in device.get("debuginfo_roots", [])
        if isinstance(device, dict)
    ]
    sysroot = (
        resolve_host_path(device.get("sysroot"), repo_root)
        if isinstance(device, dict) and device.get("sysroot")
        else None
    )
    mappings: list[dict[str, Any]] = []
    mapping_by_dso: dict[str, dict[str, Any]] = {}
    for dso, build_id in sorted(dso_build_ids.items()):
        debug_path = find_debug_file(build_id, debuginfo_roots)
        host_path = map_target_path_to_sysroot(dso, sysroot)
        mapping = {
            "target_path": dso,
            "host_path": str(host_path) if host_path is not None else "",
            "debug_path": str(debug_path) if debug_path is not None else "",
            "source_path": "",
            "build_id": build_id,
        }
        mappings.append(mapping)
        mapping_by_dso[dso] = mapping
    for sample in samples:
        for frame in sample.frames:
            mapping = mapping_by_dso.get(frame.dso)
            if mapping is None:
                continue
            debug_path = Path(mapping["debug_path"]) if mapping.get("debug_path") else None
            resolved = resolve_frame_source(
                frame=frame,
                debug_path=debug_path,
                repo_root=repo_root,
            )
            if resolved is None:
                continue
            source_path, line = resolved
            frame.file = source_path
            frame.line_start = line
            frame.line_end = line
            if not mapping["source_path"]:
                mapping["source_path"] = source_path
    return {
        "arch": arch or "",
        "backend": manifest.get("backend"),
        "sysroot": str(sysroot) if sysroot is not None else "",
        "debuginfo_roots": [str(root) for root in debuginfo_roots],
        "path_mapping": mappings,
        "bundle_dir": str(bundle_dir),
    }


def resolve_host_path(raw_path: object, repo_root: Path) -> Path:
    path = Path(str(raw_path)).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def find_debug_file(build_id: str | None, roots: Sequence[Path]) -> Path | None:
    if not build_id:
        return None
    normalized = build_id.lower()
    build_id_path = Path(".build-id") / normalized[:2] / f"{normalized[2:]}.debug"
    for root in roots:
        candidate = root / build_id_path
        if candidate.exists():
            return candidate
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and normalized in path.name.lower():
                return path
    return None


def map_target_path_to_sysroot(target_path: str, sysroot: Path | None) -> Path | None:
    if sysroot is None:
        return None
    relative = target_path.lstrip("/")
    candidate = sysroot / relative
    return candidate if candidate.exists() else candidate


def resolve_frame_source(
    *,
    frame: Frame,
    debug_path: Path | None,
    repo_root: Path,
) -> tuple[str, int] | None:
    if debug_path is not None and debug_path.exists():
        resolved = run_addr2line(debug_path, frame.ip)
        if resolved is not None:
            source_path, line = resolved
            mapped = map_source_to_repo(source_path, repo_root)
            return mapped, line
    anchor = find_source_anchor(frame.symbol, repo_root, dso=frame.dso)
    if anchor is None:
        return None
    return str(anchor["file"]), int(anchor.get("line_start", 1))


def run_addr2line(debug_path: Path, ip: str) -> tuple[str, int] | None:
    try:
        result = subprocess.run(
            ["addr2line", "-e", str(debug_path), "-f", "-C", ip],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    location = lines[1]
    if location.startswith("??"):
        return None
    match = re.match(r"(.+):(\d+)(?:\s.*)?$", location)
    if match is None:
        return None
    return match.group(1), int(match.group(2))


def map_source_to_repo(source_path: str, repo_root: Path) -> str:
    source = Path(source_path)
    if source.exists():
        try:
            return str(source.relative_to(repo_root))
        except ValueError:
            return str(source)
    candidates = [
        path
        for path in _iter_source_files(repo_root)
        if path.name == source.name or str(path).endswith(str(source).lstrip("/"))
    ]
    if len(candidates) == 1:
        return str(candidates[0].relative_to(repo_root))
    return source_path


def classify_samples(
    samples: Sequence[StackSample],
    profile: OwnershipProfile,
    dso_build_ids: dict[str, str],
) -> tuple[list[StackSample], list[OwnershipDecision]]:
    decisions_by_key: dict[tuple[str, str | None], OwnershipDecision] = {}
    classified: list[StackSample] = []
    for sample in samples:
        frames: list[Frame] = []
        for frame in sample.frames:
            build_id = dso_build_ids.get(frame.dso)
            decision = classify_ownership(frame.dso, build_id, profile)
            frame.build_id = build_id
            frame.ownership = decision.ownership
            frame.ownership_reason = decision.reason
            frames.append(frame)
            decisions_by_key[(frame.dso, build_id)] = decision
        classified.append(StackSample(frames=frames))
    return classified, list(decisions_by_key.values())


def classify_ownership(
    dso: str,
    build_id: str | None,
    profile: OwnershipProfile,
) -> OwnershipDecision:
    if build_id and _owned_build_id_known(build_id, profile):
        return OwnershipDecision(dso, build_id, "owned", f"owned_build_id:{build_id}")
    owned_rule = _first_match(dso, profile.owned_paths)
    if owned_rule is not None:
        return OwnershipDecision(dso, build_id, "owned", f"owned_paths:{owned_rule}")
    third_party_rule = _first_match(dso, profile.third_party_paths)
    if third_party_rule is not None:
        return OwnershipDecision(dso, build_id, "third-party", f"third_party_paths:{third_party_rule}")
    system_rule = _first_match(dso, profile.system_paths)
    if system_rule is not None or _looks_system_dso(dso):
        return OwnershipDecision(dso, build_id, "system", f"system_paths:{system_rule or 'builtin'}")
    return OwnershipDecision(dso, build_id, "unknown", "no matching ownership rule")


def analyze_hotspots(
    samples: Sequence[StackSample],
    *,
    profile: OwnershipProfile,
    repo_root: Path,
    total_samples: int,
    top_n: int,
    tracer: TraceLogger | None = None,
) -> list[Hotspot]:
    grouped: dict[tuple[str, str], list[StackSample]] = {}
    for sample in samples:
        if not sample.frames:
            continue
        hot = sample.frames[0]
        grouped.setdefault((hot.symbol, hot.dso), []).append(sample)

    hotspots: list[Hotspot] = []
    sorted_groups = sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), item[0][0], item[0][1]),
    )[:top_n]
    for rank, ((_symbol, _dso), group) in enumerate(sorted_groups, start=1):
        representative = _representative_stack(group)
        hot = representative.frames[0]
        code_anchor = anchor_from_frame(hot, repo_root) or find_source_anchor(
            hot.symbol,
            repo_root,
            dso=hot.dso,
        )
        attribution_anchor: dict[str, Any] | None = None
        bottleneck_class: list[str] = []
        actionability, reason = _actionability_for_hotspot(
            hot,
            representative.frames,
            profile,
            repo_root,
            code_anchor,
        )
        if hot.ownership in {"third-party", "system"}:
            attribution_frame = select_attribution_frame(representative.frames, profile)
            if attribution_frame is not None:
                attribution_anchor = anchor_from_frame(
                    attribution_frame,
                    repo_root,
                    resolution_method="caller-attribution",
                    confidence=0.80,
                    evidence=(
                        f"hot {hot.symbol} called from owned frame "
                        f"{attribution_frame.symbol}"
                    ),
                ) or find_source_anchor(
                    attribution_frame.symbol,
                    repo_root,
                    dso=attribution_frame.dso,
                    resolution_method="caller-attribution",
                    confidence=0.80,
                    evidence=(
                        f"hot {hot.symbol} called from owned frame "
                        f"{attribution_frame.symbol}"
                    ),
                )
                if attribution_anchor is not None:
                    bottleneck_class = ["external-call-overhead", "call-frequency"]
                    actionability = "actionable"
                    reason = "owned attribution frame resolved"
                else:
                    actionability = "not-actionable"
                    reason = "owned attribution frame had no source anchor"
        hotspot = Hotspot(
            rank=rank,
            samples=len(group),
            self_cpu_pct=round(len(group) * 100.0 / total_samples, 2),
            hot_frame=hot,
            representative_stack=representative.frames,
            callers=[frame.symbol for frame in representative.frames[1:]],
            actionability=actionability,
            actionability_reason=reason,
            code_anchor=code_anchor if hot.ownership == "owned" else None,
            attribution_anchor=attribution_anchor,
            bottleneck_class=bottleneck_class,
        )
        hotspots.append(hotspot)
        if tracer is not None:
            tracer.info(
                "postprocess",
                "hotspot",
                symbol=hot.symbol,
                ownership=hot.ownership,
                actionability=actionability,
                samples=len(group),
            )
    return hotspots


def select_attribution_frame(
    frames: Sequence[Frame],
    profile: OwnershipProfile,
) -> Frame | None:
    candidates = [frame for frame in frames[1:] if frame.ownership == "owned"]
    if not candidates:
        return None
    if profile.attribution_strategy == "nearest-to-entry":
        return candidates[-1]
    return candidates[0]


def find_source_anchor(
    symbol: str,
    repo_root: str | Path,
    *,
    dso: str = "",
    resolution_method: str = "ctags",
    confidence: float = 0.75,
    evidence: str | None = None,
) -> dict[str, Any] | None:
    root = Path(repo_root)
    if not root.exists():
        return None
    pattern = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    matches: list[tuple[Path, int, str]] = []
    for path in _iter_source_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            if not pattern.search(line):
                continue
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            if not _looks_like_function_definition(stripped, symbol):
                continue
            matches.append((path, line_number, stripped))
    if len(matches) != 1:
        return None
    path, line_number, matched_line = matches[0]
    try:
        file_value = str(path.relative_to(root))
    except ValueError:
        file_value = str(path)
    return {
        "symbol": symbol,
        "dso": dso,
        "file": file_value,
        "line_start": line_number,
        "line_end": line_number,
        "language": _language_for(path),
        "anchor_confidence": confidence,
        "resolution_method": resolution_method,
        "evidence": evidence or f"unique source match: {matched_line}",
    }


def anchor_from_frame(
    frame: Frame,
    repo_root: Path,
    *,
    resolution_method: str = "addr2line",
    confidence: float = 0.85,
    evidence: str | None = None,
) -> dict[str, Any] | None:
    if not frame.file or not frame.line_start:
        return None
    file_value = frame.file
    path = Path(file_value)
    if path.is_absolute():
        try:
            file_value = str(path.relative_to(repo_root))
        except ValueError:
            file_value = map_source_to_repo(str(path), repo_root)
    return {
        "symbol": frame.symbol,
        "dso": frame.dso,
        "file": file_value,
        "line_start": int(frame.line_start),
        "line_end": int(frame.line_end or frame.line_start),
        "language": _language_for(Path(file_value)),
        "anchor_confidence": confidence,
        "resolution_method": resolution_method,
        "evidence": evidence or f"{resolution_method} resolved {frame.ip}",
    }


def build_postprocess_document(
    *,
    bundle_dir: Path,
    manifest: dict[str, Any],
    hotspots: Sequence[Hotspot],
    ownership_decisions: Sequence[OwnershipDecision],
    total_samples: int,
    tizen: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = {
        "schema_version": "postprocess/v1",
        "bundle_dir": str(bundle_dir),
        "device": manifest.get("device", {}),
        "source_report": {
            "id": "perf-script",
            "path": manifest["artifacts"]["perf_script"],
            "source_format": "perf-script",
            "parser": "perf-script-callgraph",
            "confidence": 0.95,
        },
        "target": manifest["target"],
        "profiling": {
            "tool": "perf",
            "events": manifest["perf"]["events"],
            "callgraph_mode": manifest["perf"]["callgraph_mode"],
            "artifacts": manifest["artifacts"],
        },
        "run_context": manifest["run_context"],
        "total_samples": total_samples,
        "hotspots": [_hotspot_to_dict(hotspot) for hotspot in hotspots],
        "ownership_decisions": [asdict(decision) for decision in ownership_decisions],
        "provenance": {
            "generated_by": "perf-hotspot-analyzer/postprocess",
            "version": "1.0.0",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    }
    if tizen is not None:
        document["tizen"] = tizen
    return document


def write_run_report(
    *,
    output_dir: str | Path,
    trace_id: str,
    started_at: str,
    total_ms: int,
    analysis: dict[str, Any],
    exit_status: str = "success",
    errors: Sequence[str] = (),
) -> None:
    report = {
        "schema_version": "run-report/v1",
        "trace_id": trace_id,
        "skill": "perf-hotspot-analyzer",
        "started_at": started_at,
        "total_ms": total_ms,
        "by_step": {"postprocess": total_ms},
        "input": {
            "callgraph_mode": analysis["profiling"]["callgraph_mode"],
            "source_formats": ["perf-script"],
        },
        "findings": {
            "total": len(analysis["hotspots"]),
            "by_kind": {"function-hotspot": len(analysis["hotspots"])},
        },
        "anchors": _anchor_summary(analysis["hotspots"]),
        "gate_decisions": [
            {
                "finding": hotspot["id"],
                "decision": hotspot["actionability"],
                "reason": hotspot["actionability_reason"],
            }
            for hotspot in analysis["hotspots"]
        ],
        "patches": {"diff-ready": 0, "needs-review": 0, "advisory-only": 0},
        "ownership_decisions": analysis["ownership_decisions"],
        "degradations": [],
        "exit_status": exit_status,
        "errors": list(errors),
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "run-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Post-process a Capture Bundle.")
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--ownership", help="Override .perf-skill/ownership.yaml path")
    parser.add_argument("--output", required=True, help="postprocess.json path")
    parser.add_argument("--output-dir", default="out", help="Trace/run-report directory")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.monotonic()
    started_at = datetime.now(UTC).isoformat()
    tracer = start_trace(
        skill="perf-hotspot-analyzer",
        output_dir=args.output_dir,
        verbose=args.verbose,
    )
    try:
        analysis = postprocess_bundle(
            bundle_dir=args.bundle_dir,
            output=args.output,
            repo_root=args.repo_root,
            ownership_path=args.ownership,
            top_n=args.top_n,
            tracer=tracer,
        )
        write_run_report(
            output_dir=args.output_dir,
            trace_id=tracer.trace_id,
            started_at=started_at,
            total_ms=int((time.monotonic() - started) * 1000),
            analysis=analysis,
        )
    finally:
        tracer.close()
    return 0


def _finish_sample(samples: list[StackSample], frames: list[Frame]) -> None:
    if not frames:
        return
    if len(frames) >= 2 and _same_frame(frames[0], frames[1]):
        frames = frames[1:]
    samples.append(StackSample(frames=frames))


def _same_frame(left: Frame, right: Frame) -> bool:
    return left.symbol == right.symbol and left.dso == right.dso


def _normalize_symbol(symbol: str) -> str:
    if "+" in symbol:
        symbol = symbol.split("+", 1)[0]
    return symbol.strip()


def _split_srcline(value: str) -> tuple[str | None, int | None]:
    match = re.match(r"(?P<file>.+):(?P<line>\d+)$", value)
    if match is None:
        return None, None
    return match.group("file"), int(match.group("line"))


def _owned_build_id_known(build_id: str, profile: OwnershipProfile) -> bool:
    for raw_root in profile.owned_build_id_sources:
        root = Path(raw_root).expanduser()
        if any(root.parent.glob(root.name)):
            for candidate in root.parent.glob(root.name):
                if candidate.is_file() and build_id in candidate.name:
                    return True
    return False


def _first_match(value: str, patterns: Iterable[str]) -> str | None:
    for pattern in patterns:
        if fnmatch.fnmatch(value, pattern):
            return pattern
    return None


def _looks_system_dso(dso: str) -> bool:
    name = Path(dso).name
    return dso == "[kernel.kallsyms]" or name.startswith(("libc-", "ld-", "libpthread-"))


def _representative_stack(group: Sequence[StackSample]) -> StackSample:
    counts: dict[tuple[tuple[str, str], ...], int] = {}
    by_key: dict[tuple[tuple[str, str], ...], StackSample] = {}
    for sample in group:
        key = tuple((frame.symbol, frame.dso) for frame in sample.frames)
        counts[key] = counts.get(key, 0) + 1
        by_key[key] = sample
    best = max(counts, key=lambda key: (counts[key], -len(key)))
    return by_key[best]


def _actionability_for_hotspot(
    hot: Frame,
    frames: Sequence[Frame],
    profile: OwnershipProfile,
    repo_root: Path,
    code_anchor: dict[str, Any] | None,
) -> tuple[str, str]:
    if hot.ownership == "owned":
        if code_anchor is not None:
            return "actionable", "owned hotspot resolved to source"
        return "informational", "owned hotspot has no source anchor"
    if hot.ownership in {"third-party", "system"}:
        attribution = select_attribution_frame(frames, profile)
        if attribution is None:
            return "not-actionable", "no owned frame in callgraph"
        if (
            anchor_from_frame(
                attribution,
                repo_root,
                resolution_method="caller-attribution",
                confidence=0.80,
            )
            is None
            and find_source_anchor(attribution.symbol, repo_root, dso=attribution.dso)
            is None
        ):
            return "not-actionable", "owned attribution frame had no source anchor"
        return "actionable", "owned attribution frame resolved"
    return "informational", "unknown hotspot ownership"


def _iter_source_files(root: Path) -> Iterable[Path]:
    excluded = {".git", ".dev_memory", "__pycache__", ".pytest_cache"}
    for path in root.rglob("*"):
        if any(part in excluded for part in path.parts):
            continue
        if path.is_file() and path.suffix in SOURCE_SUFFIXES:
            yield path


def _looks_like_function_definition(line: str, symbol: str) -> bool:
    if line.endswith(";"):
        return False
    prefix = line.split(symbol, 1)[0].strip()
    if not prefix:
        return False
    forbidden_prefixes = ("return", "if", "while", "for", "switch")
    if prefix.split()[-1] in forbidden_prefixes:
        return False
    if any(token in prefix for token in ("=", ".", "->")):
        return False
    return True


def _language_for(path: Path) -> str:
    if path.suffix in {".cc", ".cpp", ".cxx", ".hpp", ".hh"}:
        return "c++"
    return "c"


def _hotspot_to_dict(hotspot: Hotspot) -> dict[str, Any]:
    data = {
        "id": f"H{hotspot.rank:03d}",
        "rank": hotspot.rank,
        "samples": hotspot.samples,
        "self_cpu_pct": hotspot.self_cpu_pct,
        "hot_frame": asdict(hotspot.hot_frame),
        "representative_stack": [asdict(frame) for frame in hotspot.representative_stack],
        "callers": hotspot.callers,
        "ownership": hotspot.hot_frame.ownership,
        "actionability": hotspot.actionability,
        "actionability_reason": hotspot.actionability_reason,
        "bottleneck_class": hotspot.bottleneck_class,
    }
    if hotspot.code_anchor is not None:
        data["code_anchor"] = hotspot.code_anchor
    if hotspot.attribution_anchor is not None:
        data["attribution_anchor"] = hotspot.attribution_anchor
    return data


def _anchor_summary(hotspots: Sequence[dict[str, Any]]) -> dict[str, Any]:
    resolved = 0
    buckets = {">=0.9": 0, "0.7-0.9": 0, "<0.7": 0}
    for hotspot in hotspots:
        anchor = hotspot.get("attribution_anchor") or hotspot.get("code_anchor")
        if not anchor:
            continue
        resolved += 1
        confidence = float(anchor.get("anchor_confidence", 0))
        if confidence >= 0.9:
            buckets[">=0.9"] += 1
        elif confidence >= 0.7:
            buckets["0.7-0.9"] += 1
        else:
            buckets["<0.7"] += 1
    return {"resolved": resolved, "confidence_distribution": buckets}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
