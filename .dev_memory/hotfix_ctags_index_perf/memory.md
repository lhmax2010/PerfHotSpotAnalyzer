# Hotfix Ctags Index Performance Memory

Branch: `stage/hotfix-ctags-index-perf`

## Scope

Fix a real-board regression where `find_source_anchor` still hung during
analyze on large projects with big ctags files, especially ffmpeg-scale trees.

## Completed

- ctags lookup no longer opens source files for every tag entry.
- ctags index is built from tags text only and cached as `symbol -> anchors`.
- ctags address parsing supports numeric line addresses and pattern addresses
  with `line:` extension fields.
- compile_commands indexing is only attempted after ctags lookup misses.
- fallback source search uses pruned `os.walk`, DSO-derived candidate roots, and
  hard file-count limits.
- Regression tests now cover large ctags files and no-index large-tree fallback.

## Guardrails

- No LLM SDK imports or calls were added.
- No runtime patch apply/commit/push behavior changed.
- Schema files were not changed.
