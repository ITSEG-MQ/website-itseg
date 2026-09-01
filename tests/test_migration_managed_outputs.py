import csv
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import import_legacy_content as importer  # noqa: E402
import validate_site as validator  # noqa: E402


class ManagedOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repository"
        self.repository.mkdir()
        self.old_importer_root = importer.ROOT
        self.old_validator_root = validator.ROOT
        importer.ROOT = self.repository
        validator.ROOT = self.repository

    def tearDown(self):
        importer.ROOT = self.old_importer_root
        validator.ROOT = self.old_validator_root
        self.temporary.cleanup()

    def create_managed_roots(self):
        for relative in importer.MANAGED_OUTPUT_DIRS:
            (self.repository / relative).mkdir(parents=True, exist_ok=True)

    def empty_manifest(self):
        return {
            "collections": {"news": [], "people": [], "projects": []},
            "assets": [],
        }

    def test_symlinked_managed_directory_is_refused_without_touching_target(self):
        self.create_managed_roots()
        managed = self.repository / "_news"
        managed.rmdir()
        outside = self.base / "outside"
        outside.mkdir()
        sentinel = outside / "sentinel.md"
        sentinel.write_text("outside", encoding="utf-8")
        managed.symlink_to(outside, target_is_directory=True)

        self.assertTrue(any("managed directory is a symlink" in error for error in importer.managed_root_errors()))
        self.assertTrue(any("managed directory is a symlink" in error for error in validator.managed_root_errors()))
        with self.assertRaisesRegex(SystemExit, "unsafe managed output roots"):
            importer.prepare_managed_roots()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "outside")

    def test_managed_directory_resolving_outside_repository_is_refused(self):
        for relative in importer.MANAGED_COLLECTION_DIRS:
            (self.repository / relative).mkdir(parents=True)
        (self.repository / "assets/documents").mkdir(parents=True)
        outside_pic = self.base / "outside-pic"
        for name in ["people", "projects", "brand"]:
            (outside_pic / name).mkdir(parents=True)
        (self.repository / "assets/pic").symlink_to(outside_pic, target_is_directory=True)

        errors = importer.managed_root_errors()

        self.assertTrue(any("resolves outside the repository" in error for error in errors), errors)
        with self.assertRaisesRegex(SystemExit, "unsafe managed output roots"):
            importer.prepare_managed_roots()

    def test_orphan_regular_file_and_symlink_are_unlinked_without_traversal(self):
        self.create_managed_roots()
        keep = self.repository / "_news/keep.md"
        keep.write_text("keep", encoding="utf-8")
        orphan = self.repository / "_news/orphan.txt"
        orphan.write_text("orphan", encoding="utf-8")
        outside = self.base / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        orphan_link = self.repository / "assets/documents/orphan-link.pdf"
        orphan_link.symlink_to(outside)

        importer.remove_unexpected_managed_files({"_news/keep.md"})

        self.assertTrue(keep.is_file())
        self.assertFalse(orphan.exists())
        self.assertFalse(orphan_link.is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_validator_rejects_orphan_in_managed_directory(self):
        self.create_managed_roots()
        (self.repository / "_projects/orphan.bin").write_bytes(b"orphan")

        errors = validator.managed_output_errors(self.empty_manifest())

        self.assertTrue(any("extra=['orphan.bin']" in error for error in errors), errors)


class LegacyUrlMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((PROJECT_ROOT / "docs/content-manifest.yml").read_text(encoding="utf-8"))
        cls.records = {}
        specifications = {
            "news": ["title", "date", "legacy_id", "source_order", "cover", "permalink", "source_status"],
            "people": ["title", "role", "category", "section", "image", "order", "permalink", "source_status", "source_records"],
            "projects": ["title", "category", "image", "order", "permalink", "source_status"],
        }
        for kind, required in specifications.items():
            _, found, errors = validator.collection_errors(kind, required)
            if errors:
                raise AssertionError(errors)
            cls.records[kind] = found
        cls.expected = validator.expected_url_map_rows(cls.records, cls.manifest["assets"])

    def write_map(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(validator.URL_MAP_HEADER)
            writer.writerows(rows)

    def test_exact_url_map_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy-url-map.csv"
            self.write_map(path, self.expected)
            self.assertEqual(
                validator.legacy_url_map_errors(self.records, self.manifest["assets"], path),
                [],
            )

    def test_duplicate_extra_and_missing_url_map_rows_are_rejected(self):
        reordered = list(self.expected)
        reordered[5], reordered[6] = reordered[6], reordered[5]
        variants = {
            "duplicate": self.expected + [self.expected[5]],
            "extra": self.expected + [("/arbitrary", "/extra/", "page", "migrated", "unexpected")],
            "missing": self.expected[:-1],
            "reordered": reordered,
        }
        with tempfile.TemporaryDirectory() as temporary:
            for name, rows in variants.items():
                with self.subTest(name=name):
                    path = Path(temporary) / f"{name}.csv"
                    self.write_map(path, rows)
                    errors = validator.legacy_url_map_errors(
                        self.records, self.manifest["assets"], path
                    )
                    self.assertTrue(errors, name)
                    if name != "reordered":
                        self.assertTrue(any("exactly match" in error for error in errors), errors)
                    else:
                        self.assertTrue(any("row order" in error for error in errors), errors)
                    if name == "duplicate":
                        self.assertTrue(any("duplicate" in error for error in errors), errors)

    def test_reordered_manifest_collections_are_rejected(self):
        for kind in ["news", "people", "projects"]:
            with self.subTest(kind=kind):
                manifest = copy.deepcopy(self.manifest)
                manifest["collections"][kind][0], manifest["collections"][kind][1] = (
                    manifest["collections"][kind][1],
                    manifest["collections"][kind][0],
                )
                errors = validator.manifest_errors(self.records, manifest)
                self.assertTrue(
                    any(f"manifest {kind} collection" in error and "canonical" in error for error in errors),
                    errors,
                )

    def test_reordered_manifest_assets_are_rejected(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["assets"][0], manifest["assets"][1] = manifest["assets"][1], manifest["assets"][0]

        errors = validator.manifest_errors(self.records, manifest)

        self.assertTrue(any("manifest assets are not in canonical source order" in error for error in errors), errors)

    def test_coordinated_manifest_and_url_map_reordering_is_rejected(self):
        cases = [("news", 5), ("assets", 5 + len(self.records["news"]))]
        with tempfile.TemporaryDirectory() as temporary:
            for collection, row_index in cases:
                with self.subTest(collection=collection):
                    manifest = copy.deepcopy(self.manifest)
                    manifest_key = "news" if collection == "news" else None
                    entries = (
                        manifest["collections"][manifest_key]
                        if manifest_key
                        else manifest["assets"]
                    )
                    entries[0], entries[1] = entries[1], entries[0]
                    rows = list(self.expected)
                    rows[row_index], rows[row_index + 1] = rows[row_index + 1], rows[row_index]
                    path = Path(temporary) / f"coordinated-{collection}.csv"
                    self.write_map(path, rows)

                    manifest_errors = validator.manifest_errors(self.records, manifest)
                    url_errors = validator.legacy_url_map_errors(
                        self.records, manifest["assets"], path
                    )

                    self.assertTrue(manifest_errors, collection)
                    self.assertTrue(any("row order" in error for error in url_errors), url_errors)


if __name__ == "__main__":
    unittest.main()
