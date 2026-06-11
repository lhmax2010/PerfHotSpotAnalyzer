from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BINARY_SIZE_PATH = (
    ROOT / "skills" / "perf-hotspot-analyzer" / "scripts" / "binary_size.py"
)


def load_binary_size_module():
    spec = importlib.util.spec_from_file_location("a2_binary_size", BINARY_SIZE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


READELF_SAMPLE = """
There are 8 section headers, starting at offset 0x22428:

Section Headers:
  [Nr] Name              Type            Address          Off    Size   ES Flg Lk Inf Al
  [ 1] .interp           PROGBITS        0000000000000318 000318 00001c 00   A  0   0  1
  [ 2] .text             PROGBITS        0000000000004000 004000 001000 00  AX  0   0 16
  [ 3] .rodata           PROGBITS        0000000000005000 005000 000800 00   A  0   0 32
  [ 4] .data             PROGBITS        0000000000006000 006000 000040 00  WA  0   0  8
  [ 5] .bss              NOBITS          0000000000007000 006040 000120 00  WA  0   0 32
  [ 6] .debug_info       PROGBITS        0000000000000000 006040 004000 00      0   0  1
"""


def test_parse_readelf_sections_reads_size_flags_and_alignment() -> None:
    binary_size = load_binary_size_module()

    sections = binary_size.parse_readelf_sections(READELF_SAMPLE)

    text = next(section for section in sections if section.name == ".text")
    assert text.size == 0x1000
    assert text.flags == "AX"
    assert text.align == 16
    assert text.is_alloc


def test_alloc_sections_include_nobits_and_skip_debug() -> None:
    binary_size = load_binary_size_module()
    sections = binary_size.parse_readelf_sections(READELF_SAMPLE)

    alloc = binary_size.alloc_sections(sections)

    assert [section.name for section in alloc] == [
        ".interp",
        ".text",
        ".rodata",
        ".data",
        ".bss",
    ]
    assert ".debug_info" not in [section.name for section in alloc]


def test_total_alloc_size_sums_alloc_section_bytes() -> None:
    binary_size = load_binary_size_module()
    sections = binary_size.parse_readelf_sections(READELF_SAMPLE)

    assert binary_size.total_alloc_size(sections) == 0x1C + 0x1000 + 0x800 + 0x40 + 0x120


def test_parse_section_line_ignores_headers_and_malformed_lines() -> None:
    binary_size = load_binary_size_module()

    assert binary_size.parse_readelf_section_line("Section Headers:") is None
    assert binary_size.parse_readelf_section_line("  [Nr] Name Type Address") is None
    assert binary_size.parse_readelf_section_line("  [ 9] malformed") is None


def test_section_map_keeps_sections_by_name() -> None:
    binary_size = load_binary_size_module()
    sections = binary_size.parse_readelf_sections(READELF_SAMPLE)

    mapped = binary_size.section_map(sections)

    assert mapped[".rodata"].size == 0x800
