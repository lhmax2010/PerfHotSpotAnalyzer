# perf-optimization-pipeline

M0 skeleton for the non-triggerable workflow. The workflow has no `SKILL.md` and
only exposes contract validation through the CLI.

```bash
python -m perf_optimization_pipeline validate --document-type performance-findings --input performance-findings.json
python -m perf_optimization_pipeline validate --document-type suggestion-patch --input patches.json
```

