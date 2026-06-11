# A2 binary-size Test Guide

## Scope

A2 validates static ELF binary-size findings:

- single ELF `binary-size-large`
- current/baseline ELF `binary-size-regression`

It does not run perf, touch Tizen transport, generate source anchors, or call any
LLM API.

## Prerequisites

- Linux host with `readelf`.
- `size` for optional section-byte cross-checks.
- `gcc` only if rebuilding fixtures.

## Deterministic CI Path

```bash
pytest tests/functional/test_a2_binary_size.py -q
```

Expected result: 2 passed.

Manual commands:

```bash
python3 -m cli.perf_hotspot_analyzer binary-size \
  --elf tests/fixtures/golden/live-perf/binary-size/bin/topn.elf \
  --repo-root tests/fixtures/golden/live-perf/binary-size \
  --ownership tests/fixtures/golden/live-perf/binary-size/.perf-skill/ownership.yaml \
  --output-dir /tmp/a2-large

python3 -m cli.perf_hotspot_analyzer binary-size \
  --elf tests/fixtures/golden/live-perf/binary-size/bin/after.elf \
  --baseline tests/fixtures/golden/live-perf/binary-size/bin/before.elf \
  --repo-root tests/fixtures/golden/live-perf/binary-size \
  --ownership tests/fixtures/golden/live-perf/binary-size/.perf-skill/ownership.yaml \
  --output-dir /tmp/a2-regression
```

Pass criteria:

- Both `performance-findings.json` files validate with `common/schema_validate.py`.
- `topn.elf` emits five `binary-size-large` findings with `threshold.type=top-n`.
- Top-n findings are `informational`.
- Regression emits `.inflate` with delta 6144 bytes / 300% increase.
- Regression finding is `actionable`.

## Rebuilding Fixtures

```bash
tests/fixtures/golden/live-perf/binary-size/build.sh
```

After rebuild, rerun:

```bash
pytest tests/functional/test_a2_binary_size.py -q
```

## Debug Logs

Each CLI run writes:

- `<output-dir>/performance-findings.json`
- `<output-dir>/analysis-report.md`
- `<output-dir>/run-report.json`
- `<output-dir>/run-<trace_id>.jsonl`

Attach those files plus the ELF inputs for review.
