# Hotfix Ctags Index Performance Decisions

## Ctags Lookup Must Not Reopen Source Files

- Root cause: the previous P0 hotfix read `tags`, then called
  `_find_symbol_in_file()` for each ctags entry. On ffmpeg-scale tags files
  this caused hundreds of thousands of file opens and regex scans before the
  current hotspot symbol was even queried.
- Fix: `_index_from_ctags()` now parses the ctags line directly. It uses numeric
  addresses such as `123;"` and pattern addresses with `line:<n>` extension
  fields to create anchors without opening source files.
- Test: `test_find_source_anchor_uses_large_ctags_without_reopening_sources`
  creates an 8,000-symbol tags file, monkeypatches `_find_symbol_in_file()` to
  fail if called, and verifies lookup completes under 2 seconds.

## Keep Indexing On-Demand Enough For Analyze

- Root cause: a full source-backed index made startup cost proportional to the
  whole repository instead of the handful of hot symbols.
- Fix: ctags lookup is now a one-time pure text parse cached by repo root, and
  compile_commands scanning is only used after ctags fails to provide a unique
  match.
- Test: existing compile_commands large-tree coverage still passes, while the
  new ctags test proves ctags hits bypass source scans.

## Fallback Search Must Be Bounded

- Root cause: fallback still relied on broad tree enumeration and only partly
  limited the result set, so large repos could spend too long walking irrelevant
  directories.
- Fix: fallback now prunes `.git`, build, docs, tests, cache, and dependency
  directories; derives DSO tokens such as `libavcodec`/`avcodec`; searches
  matching source directories first; and stops at hard file/dir limits.
- Test: `test_find_source_anchor_fallback_prefers_dso_directory_on_large_tree`
  builds a large no-index tree and verifies the libavcodec target resolves
  under 2 seconds.
