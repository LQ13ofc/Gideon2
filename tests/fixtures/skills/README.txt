TEST FIXTURES ONLY. Synthetic D1 skill manifests for the S4 gates.
Never shipped, never installed by default, never published as a catalog.

Layout:
  valid/     manifests the D1 rules must accept (catalog-free or with catalog/ helpers)
  invalid/   one manifest per negative rule; file name = fixture case (see scripts/skillfix.py REASON_MAP)
  catalog/   installed-skill helpers referenced by skill: calls (depth chain); valid on their own
  oversize   not stored: scripts/skillfix.py generates it (file > 16 KiB)

Checked by: scripts/skillfix.py (reference validator) and scripts/test_skillfix.py.
Do not copy these files into any package, catalog or skills/ directory.
