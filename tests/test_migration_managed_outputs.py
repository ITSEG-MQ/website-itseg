import csv
import copy
import html
import json
import shutil
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

    def test_stale_manifested_outputs_are_unlinked_without_traversal(self):
        self.create_managed_roots()
        keep = self.repository / "_news/keep.md"
        keep.write_text("keep", encoding="utf-8")
        orphan = self.repository / "_news/orphan.txt"
        orphan.write_text("orphan", encoding="utf-8")
        outside = self.base / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        orphan_link = self.repository / "assets/documents/orphan-link.pdf"
        orphan_link.symlink_to(outside)

        importer.remove_stale_legacy_outputs(
            {"_news/keep.md", "_news/orphan.txt", "assets/documents/orphan-link.pdf"},
            {"_news/keep.md"},
        )

        self.assertTrue(keep.is_file())
        self.assertFalse(orphan.exists())
        self.assertFalse(orphan_link.is_symlink())
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_valid_editorial_record_survives_repeated_importer_cleanup(self):
        self.create_managed_roots()
        upload = self.repository / "assets/uploads/news/editorial-cover.jpg"
        upload.parent.mkdir(parents=True)
        upload.write_bytes(b"editorial image")
        editorial = self.repository / "_news/editorial-update.md"
        importer.write_markdown(
            editorial,
            {
                "managed_by": "editorial",
                "id": "editorial-update",
                "title": "Editorial update",
                "date": "2026-09-01",
                "cover": "/assets/uploads/news/editorial-cover.jpg",
                "permalink": "/news/editorial-update/",
            },
            "A valid editorial news item.",
        )
        stale = self.repository / "_news/stale-legacy.md"
        stale.write_text("stale", encoding="utf-8")
        previous = {"_news/stale-legacy.md", "_news/editorial-update.md"}

        importer.remove_stale_legacy_outputs(previous, set())
        importer.remove_stale_legacy_outputs(previous, set())

        self.assertTrue(editorial.is_file())
        self.assertFalse(stale.exists())
        _, records, errors = validator.collection_errors(
            "news",
            ["title", "date", "legacy_id", "source_order", "cover", "permalink", "source_status"],
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0][1]["managed_by"], "editorial")

    def test_unlisted_file_falsely_marked_legacy_import_is_rejected(self):
        self.create_managed_roots()
        cover = self.repository / "assets/pic/brand/imposter.jpg"
        cover.write_bytes(b"imposter")
        importer.write_markdown(
            self.repository / "_news/imposter.md",
            {
                "managed_by": "legacy-import",
                "title": "Unlisted legacy impostor",
                "date": "2026-09-01",
                "legacy_id": "999",
                "source_order": 999,
                "cover": "/assets/pic/brand/imposter.jpg",
                "permalink": "/news/unlisted-legacy-impostor/",
                "source_status": "legacy-public-export",
            },
            "This file is not in the immutable manifest.",
        )
        _, news, parse_errors = validator.collection_errors(
            "news",
            ["title", "date", "legacy_id", "source_order", "cover", "permalink", "source_status"],
        )
        self.assertEqual(parse_errors, [])

        errors = validator.managed_output_errors(
            self.empty_manifest(),
            {"news": news, "people": [], "projects": []},
        )

        self.assertTrue(any("legacy-import files differ" in error and "imposter.md" in error for error in errors), errors)

    def test_validator_rejects_orphan_in_managed_directory(self):
        self.create_managed_roots()
        (self.repository / "_projects/orphan.bin").write_bytes(b"orphan")

        errors = validator.managed_output_errors(self.empty_manifest())

        self.assertTrue(any("unexpected non-Markdown" in error and "orphan.bin" in error for error in errors), errors)


class EditorialPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name)
        (self.repository / "_data").mkdir()
        self.old_root = validator.ROOT
        self.old_importer_root = importer.ROOT
        self.old_publications_source = importer.PUBLIC_SOURCE_FILES["publications"]
        validator.ROOT = self.repository
        importer.ROOT = self.repository

        baseline = json.loads(
            (PROJECT_ROOT / "_data/publications.yml").read_text(encoding="utf-8")
        )
        source = self.repository / "legacy-publications.html"
        chunks = []
        current_category = None
        for publication in baseline:
            if publication["category"] != current_category:
                current_category = publication["category"]
                chunks.append(f"<h2>{html.escape(current_category)}</h2>")
            chunks.append(
                '<div class="caption">'
                f'<p class="title">{html.escape(publication["title"])}</p>'
                f'<p class="authors">{html.escape(publication["authors"])}</p>'
                f'<p class="publisher">{html.escape(publication["publisher"])}</p>'
                "</div>"
            )
        source.write_text("\n".join(chunks), encoding="utf-8")
        importer.PUBLIC_SOURCE_FILES["publications"] = source

    def tearDown(self):
        validator.ROOT = self.old_root
        importer.ROOT = self.old_importer_root
        importer.PUBLIC_SOURCE_FILES["publications"] = self.old_publications_source
        self.temporary.cleanup()

    def write_publications(self, extra):
        baseline = json.loads((PROJECT_ROOT / "_data/publications.yml").read_text(encoding="utf-8"))
        (self.repository / "_data/publications.yml").write_text(
            json.dumps([*baseline, *extra], indent=2) + "\n",
            encoding="utf-8",
        )

    def test_valid_editorial_publication_is_allowed(self):
        self.write_publications(
            [
                {
                    "managed_by": "editorial",
                    "id": "publication-2026-editorial-example",
                    "title": "Editorial example",
                    "authors": "A. Author",
                    "publisher": "Example Journal, 2026",
                    "category": "Refereed Journal Articles",
                }
            ]
        )

        publications, errors = validator.publication_errors()

        self.assertEqual(errors, [])
        self.assertEqual(len(publications), 117)

    def test_editorial_publication_survives_two_importer_reruns(self):
        editorial = {
            "managed_by": "editorial",
            "id": "publication-2026-editorial-example",
            "title": "Editorial example",
            "authors": "A. Author",
            "publisher": "Example Journal, 2026",
            "category": "Refereed Journal Articles",
        }
        self.write_publications([editorial])

        importer.import_publications()
        importer.import_publications()
        publications, errors = validator.publication_errors()

        self.assertEqual(errors, [])
        self.assertEqual(publications[-1], editorial)

    def test_editorial_publication_id_collision_and_unknown_category_are_rejected(self):
        self.write_publications(
            [
                {
                    "managed_by": "editorial",
                    "id": "publication-001",
                    "title": "Collision",
                    "authors": "A. Author",
                    "publisher": "Example Journal, 2026",
                    "category": "Unsupported Category",
                }
            ]
        )

        _, errors = validator.publication_errors()

        self.assertTrue(any("ids are not unique" in error for error in errors), errors)
        self.assertTrue(any("existing rendered publication categories" in error for error in errors), errors)


class EditorialCollectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary.name)
        for relative in ["_news", "_people", "_projects", "assets", "docs"]:
            shutil.copytree(PROJECT_ROOT / relative, self.repository / relative)
        self.old_root = validator.ROOT
        self.old_importer_root = importer.ROOT
        validator.ROOT = self.repository
        importer.ROOT = self.repository

    def tearDown(self):
        validator.ROOT = self.old_root
        importer.ROOT = self.old_importer_root
        self.temporary.cleanup()

    def add_editorial_record(self, kind, identifier, fields, body):
        asset_field = "cover" if kind == "news" else "image"
        asset = self.repository / fields[asset_field].lstrip("/")
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(b"editorial image")
        importer.write_markdown(
            self.repository / f"_{kind}/{identifier}.md",
            {"managed_by": "editorial", "id": identifier, **fields},
            body,
        )

    def test_all_valid_editorial_collection_types_pass_baseline_aware_validation(self):
        self.add_editorial_record(
            "news",
            "editorial-news",
            {
                "title": "Editorial news",
                "date": "2026-09-01",
                "cover": "/assets/uploads/news/editorial-news.jpg",
                "permalink": "/news/editorial-news/",
            },
            "Editorial news body.",
        )
        self.add_editorial_record(
            "people",
            "editorial-person",
            {
                "title": "Dr Editorial Person",
                "role": "Research Fellow",
                "category": "program-leaders",
                "section": "Program Leaders",
                "image": "/assets/uploads/people/editorial-person.jpg",
                "order": 38,
                "permalink": "/people/editorial-person/",
            },
            "Editorial biography.",
        )
        self.add_editorial_record(
            "projects",
            "editorial-project",
            {
                "title": "Editorial Project",
                "category": "other",
                "section": "Other Projects",
                "image": "/assets/uploads/projects/editorial-project.jpg",
                "order": 9,
                "permalink": "/projects/editorial-project/",
            },
            "Editorial project description.",
        )
        specifications = {
            "news": ["title", "date", "legacy_id", "source_order", "cover", "permalink", "source_status"],
            "people": ["title", "role", "category", "section", "image", "order", "permalink", "source_status", "source_records"],
            "projects": ["title", "category", "image", "order", "permalink", "source_status"],
        }
        records = {}
        errors = []
        for kind, required in specifications.items():
            _, records[kind], found_errors = validator.collection_errors(kind, required)
            errors.extend(found_errors)
        errors.extend(validator.collection_semantic_errors(records))
        errors.extend(validator.manifest_errors(records))

        self.assertEqual(errors, [])

    def test_live_people_count_can_change_without_altering_provenance_manifest(self):
        people = sorted((self.repository / "_people").glob("*.md"))
        for path in people[:3]:
            path.unlink()

        specifications = {
            "news": ["title", "date", "legacy_id", "source_order", "cover", "permalink", "source_status"],
            "people": ["title", "role", "category", "section", "image", "order", "permalink", "source_status", "source_records"],
            "projects": ["title", "category", "image", "order", "permalink", "source_status"],
        }
        records = {}
        errors = []
        for kind, required in specifications.items():
            _, records[kind], found_errors = validator.collection_errors(kind, required)
            errors.extend(found_errors)
        errors.extend(validator.collection_semantic_errors(records))
        errors.extend(validator.manifest_errors(records))

        self.assertEqual(errors, [])
        self.assertEqual(len(records["people"]), len(people) - 3)


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


class SanitizedContentAndGeneratedHtmlTests(unittest.TestCase):
    def test_internal_publications_link_uses_relative_url_liquid(self):
        expected = "{{ '/publications/' | relative_url }}"
        for source in [
            "http://itseg.org/publications.php",
            "https://www.itseg.org/publications.php#journals",
            "/publications.php",
        ]:
            with self.subTest(source=source):
                result = importer.sanitized_href(source)
                self.assertEqual(
                    result,
                    expected + ("#journals" if source.endswith("#journals") else ""),
                )

        rendered = importer.sanitize_html_fragment(
            '<p>Read <a href="http://itseg.org/publications.php">more</a>.</p>'
        )
        self.assertIn(f'<a href="{expected}">more</a>', rendered)
        migrated_news = (
            PROJECT_ROOT / "_news/2022-01-08-4-media-reports.md"
        ).read_text(encoding="utf-8")
        self.assertIn(f'<a href="{expected}">More Publications</a>', migrated_news)
        self.assertNotIn('<a href="/publications/">More Publications</a>', migrated_news)

    def test_configured_baseurl_is_stripped_when_resolving_generated_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site = root / "_site"
            page = site / "news/item/index.html"
            target = site / "publications/index.html"
            page.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            page.write_text("", encoding="utf-8")
            target.write_text("", encoding="utf-8")
            config = root / "config.yml"
            config.write_text('baseurl: "/preview-site"\n', encoding="utf-8")

            baseurl = validator.configured_baseurl(config)
            candidates = validator.candidate_targets(
                site, page, "/preview-site/publications/", baseurl
            )

            self.assertEqual(baseurl, "/preview-site")
            self.assertIn(target, candidates)

    def test_quoted_malicious_metadata_remains_one_escaped_attribute(self):
        fixture = {
            "title": 'Dr "Quoted" <img src=x onerror=alert(1)> & Co',
            "role": 'Lead "Researcher" <script>alert(1)</script>',
        }
        rendered = (
            '<article><img src="/portrait.jpg" alt="Portrait of '
            + html.escape(fixture["title"], quote=True)
            + '" width="480" height="560" loading="lazy">'
            + "<p>"
            + html.escape(fixture["role"], quote=True)
            + "</p></article>"
        )
        parser = validator.DocumentParser()
        parser.feed(rendered)
        parser.close()

        self.assertEqual(parser.errors, [])
        self.assertEqual(parser.images[0]["alt"], f'Portrait of {fixture["title"]}')
        self.assertNotIn("script", parser.tags)

    def test_generated_parser_rejects_malformed_attributes_and_unsafe_schemes(self):
        malicious_fixture = (
            '<a href="javascript:alert(1)" onfocus="alert(2)">bad</a>'
            '<img src="/safe.jpg" alt alt="duplicate">'
        )
        parser = validator.DocumentParser()
        parser.feed(malicious_fixture)
        parser.close()

        self.assertTrue(any("unsafe scheme" in error for error in parser.errors), parser.errors)
        self.assertTrue(any("event-handler" in error for error in parser.errors), parser.errors)
        self.assertTrue(any("duplicate attributes" in error for error in parser.errors), parser.errors)
        self.assertTrue(any("has no value" in error for error in parser.errors), parser.errors)

    def test_generated_validator_reports_unsafe_scheme_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            site = root / "site"
            config = root / "config.yml"
            config.write_text('baseurl: ""\nenvironment: "staging"\n', encoding="utf-8")
            document = """<!doctype html>
<html><head><title>Fixture</title>
<meta name="viewport" content="width=device-width">
<meta name="description" content="Fixture">
<meta name="theme-color" content="#fff">
<meta name="robots" content="noindex,nofollow">
<meta property="og:title" content="Fixture">
<link rel="canonical" href="https://example.test/">
</head><body><a href="#main-content">Skip</a><main id="main-content">
<a href="javascript:alert(1)">Unsafe fixture</a>
</main></body></html>"""
            for relative in validator.REQUIRED_PAGES:
                path = site / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(document, encoding="utf-8")
            (site / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
            (site / "sitemap.xml").write_text("<urlset/>\n", encoding="utf-8")

            errors = validator.generated_errors(site, {}, config)

            self.assertEqual(len(errors), len(validator.REQUIRED_PAGES), errors)
            self.assertTrue(all("unsafe scheme 'javascript'" in error for error in errors))

    def test_sanitizer_unwraps_unsafe_link_but_preserves_safe_body_markup(self):
        fragment = (
            '<p>Hello <strong>team</strong> '
            '<a href="jav&#x61;script:alert(1)" onclick="bad()">link</a>.</p>'
        )
        sanitized = importer.sanitize_html_fragment(fragment)

        self.assertEqual(sanitized, "<p>Hello <strong>team</strong> link.</p>")


if __name__ == "__main__":
    unittest.main()
