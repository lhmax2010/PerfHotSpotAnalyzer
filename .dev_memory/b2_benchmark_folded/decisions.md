# B2 Decisions

## Google Benchmark

- `baseline_report` present means emit `benchmark-regression` findings with `comparison.baseline_report`.
- Without baseline, emit `benchmark-latency`; Gate records `benchmark-latency-without-perf-budget`.
- `renamed_map` supports both `current -> baseline` and `baseline -> current` lookup.
- Baseline reports are registered as a second `source_reports` entry for traceability.

## Folded Stacks

- Folded stack samples aggregate by leaf symbol.
- Without deterministic repo-root source anchor, findings remain `actionability=informational`.
- If repo-root search adds a source anchor, function-hotspot findings are upgraded to `ownership=owned` and `actionability=actionable`.

## Generic LLM

- The script never normalizes free-form text itself and never imports an LLM SDK.
- First pass writes `prompts/<id>-normalize.prompt.md`.
- The script waits for `outputs/<id>-normalized.json`; missing output raises a pending error.
- Read-back JSON is forced to `source_format=generic-llm`, `parser=generic-llm`, and parser confidence 0.30.

## Anchor Search

- `reported_anchor_confidence` remains the upstream/input value; `anchor_confidence` is the rubric-scored value used by Gate.
- Equivalent anchors with different `resolution_method` are kept separately so deterministic re-anchors can supersede generic guesses.
- `bench-name-map` is intentionally scored 0.50 by rubric, so it usually remains advisory without a stronger deterministic anchor.
