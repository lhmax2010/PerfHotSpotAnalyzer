# B2 Known Issues

- None blocking for B2.

## Deferred by Design

- B3 will decide patch categories and generate reviewable diffs.
- B2 does not run or validate build/test/benchmark commands.
- Free-form generic-llm normalization still depends on the host Agent writing `outputs/<id>-normalized.json`.
- Repo-root source search is deterministic and conservative; broad/multi-candidate matches remain advisory.
