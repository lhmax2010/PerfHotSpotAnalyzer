---
name: perf-suggestion-patch
description: >-
  Analyze a code-related performance or benchmark report and, when the source
  anchor is reliable, generate review-style suggestion patches against a
  codebase.
---

# perf-suggestion-patch

M0 skeleton only. The skill owns `schemas/suggestion-patch.schema.json` and a
byte-identical copy of `schemas/performance-findings.schema.json`; validation is
performed through `common/schema_validate.py`.

Implemented entrypoint:

```bash
python -m perf_suggestion_patch validate --input patches.json
python -m perf_suggestion_patch validate --document-type performance-findings --input performance-findings.json
```

No LLM calls, patch generation, automatic apply, commit, or push behavior exists
in M0.
