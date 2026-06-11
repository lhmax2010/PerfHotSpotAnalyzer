# A2 binary-size fixture

This directory contains real pre-generated x86_64 ELF files for A2:

- `bin/topn.elf`: many small allocated sections, intended to trigger only
  top-n `binary-size-large` findings.
- `bin/before.elf` and `bin/after.elf`: same program with `.inflate` larger in
  the current build, intended to trigger `binary-size-regression`.

The C sources are kept beside the binaries so reviewers can rebuild locally.
