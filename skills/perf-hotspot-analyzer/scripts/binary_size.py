"""Binary size analysis for ELF section findings."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


READ_TIMEOUT_S = 20


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
