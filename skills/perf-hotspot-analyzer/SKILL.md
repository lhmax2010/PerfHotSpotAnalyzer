---
name: perf-hotspot-analyzer
description: >-
  Profile a native C/C++/Rust module on Linux/Tizen with perf to locate CPU
  hotspots, and statically scan ELF section/binary size, then diagnose
  bottlenecks against the source and emit a structured performance-findings
  report (JSON + Markdown + flamegraph).
---

# perf-hotspot-analyzer

M0 skeleton only. The skill owns the analyzer-facing copy of
`schemas/performance-findings.schema.json` and validates documents through
`common/schema_validate.py`.

Implemented entrypoint:

```bash
python -m perf_hotspot_analyzer validate --input performance-findings.json
```

No profiler capture, LLM calls, Tizen device flow, or patch application exists in
M0.
