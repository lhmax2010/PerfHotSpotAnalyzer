# Hotfix Effective Anchor Handoff Known Issues

- Patch generation still emits advisory entries for lower-priority findings to
  preserve existing B1/M-final review-package contracts. Owned/actionable
  findings are ordered first; system/not-actionable entries are pushed to the
  end.
- A-originated reports without host-provided `candidate_optimizations` stay
  advisory-only even when their anchors are high confidence. This is intentional
  because A does not generate optimization strategies.

