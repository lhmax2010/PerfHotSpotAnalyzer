# Hotfix Ctags Index Performance Known Issues

- Pattern-only ctags addresses without a `line:<n>` extension cannot encode an
  exact source line without opening the source file. The hotfix avoids source
  reopening and uses line 1 for those entries, with evidence indicating a
  pattern address. Universal ctags with `line:<n>` preserves exact line numbers.
