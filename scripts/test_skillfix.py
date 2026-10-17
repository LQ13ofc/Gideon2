#!/usr/bin/env python3
"""Cross-checks the synthetic D1 skill fixtures against the reference validator (stdlib unittest).

TEST ONLY. Run: python3 scripts/test_skillfix.py
"""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skillfix as sf  # noqa: E402


class FixtureSetTests(unittest.TestCase):
    def test_every_valid_file_passes(self):
        valid = sf.all_valid()
        self.assertTrue(valid)
        for stem, manifest in valid.items():
            with self.subTest(stem=stem):
                self.assertIsNone(sf.reference_validate(manifest))

    def test_every_invalid_file_fails_with_its_mapped_reason(self):
        invalid = sf.all_invalid()
        self.assertTrue(invalid)
        for stem, manifest in invalid.items():
            with self.subTest(stem=stem):
                self.assertEqual(sf.reference_validate(manifest), sf.REASON_MAP[stem])

    def test_invalid_set_is_exactly_the_mapping_table(self):
        self.assertEqual(set(sf.all_invalid()), set(sf.REASON_MAP))

    def test_mapped_reasons_are_closed_set(self):
        self.assertLessEqual(set(sf.REASON_MAP.values()), sf.REASONS)

    def test_catalog_helpers_are_valid_on_their_own(self):
        catalog = sf.all_catalog()
        self.assertEqual(set(catalog), {"depth_mid1", "depth_mid2", "depth_leaf"})
        for stem, manifest in catalog.items():
            with self.subTest(stem=stem):
                self.assertIsNone(sf.reference_validate(manifest))

    def test_manifest_ids_are_unique_across_fixtures(self):
        everything = list(sf.all_valid().values()) + list(sf.all_invalid().values()) + list(
            sf.all_catalog().values())
        ids = [m.get("id") for m in everything]
        self.assertEqual(len(ids), len(set(ids)))

    def test_oversize_is_really_over_limit(self):
        size = len(json.dumps(sf.load("invalid/oversize"), indent=2, ensure_ascii=False).encode())
        self.assertGreater(size, 16 * 1024)

    def test_stored_files_are_under_limit(self):
        for group in ("valid", "invalid", "catalog"):
            for stem in sf._stems(group):
                with self.subTest(group=group, stem=stem):
                    self.assertLessEqual(sf.ROOT.joinpath(group, stem + ".json").stat().st_size,
                                         16 * 1024)


class RuleSanityTests(unittest.TestCase):
    def setUp(self):
        self.base = copy.deepcopy(sf.load("valid/uses_stub_plugin"))

    def test_schema_version_flip(self):
        self.base["schema_version"] = True
        self.assertEqual(sf.reference_validate(self.base), "schema_version")

    def test_cycle_needs_installed_catalog(self):
        cycle_a = sf.load("invalid/cycle_a")
        self.assertIsNone(sf.reference_validate(cycle_a, catalog={}))
        self.assertEqual(sf.reference_validate(cycle_a), "cycle")

    def test_missing_dependency_does_not_invalidate(self):
        self.assertIsNone(sf.reference_validate(sf.load("valid/missing_dep")))

    def test_template_to_earlier_step_is_ok_and_self_verify_is_ok(self):
        self.assertIsNone(sf.reference_validate(sf.load("valid/read_process_write")))

    def test_core_code_prefix(self):
        self.assertEqual(sf.core_code("depth"), "skill_invalid:depth")


if __name__ == "__main__":
    unittest.main()
