import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


class SiteContractTests(unittest.TestCase):
    def test_public_pages_and_retired_routes(self):
        for relative in [
            "index.html",
            "news/index.html",
            "people/index.html",
            "projects/index.html",
            "publications/index.html",
            "contact/index.html",
            "404.html",
            "robots.txt",
            "sitemap.xml",
        ]:
            self.assertTrue((ROOT / relative).is_file(), relative)
        for relative in ["archive", "committee", "program", "registration", "venue"]:
            self.assertFalse((ROOT / relative).exists(), relative)

    def test_both_configs_define_the_same_site_contract(self):
        staging = (ROOT / "_config.yml").read_text(encoding="utf-8")
        production = (ROOT / "_config_prod.yml").read_text(encoding="utf-8")
        for text in [staging, production]:
            for required in [
                "ITSEG — Intelligent Systems Engineering Group",
                "collections:",
                "news:",
                "people:",
                "projects:",
                "output: true",
                "layout: news",
                "layout: person",
                "layout: project",
                "james.zheng@mq.edu.au",
                "+61 2 9850 6330",
            ]:
                self.assertIn(required, text)
        self.assertIn('url: "https://itseg-mq.github.io"', staging)
        self.assertIn('baseurl: "/website-itseg"', staging)
        self.assertIn('url: "https://beta.itseg.org"', production)
        self.assertIn('baseurl: ""', production)

    def test_navigation_is_data_driven(self):
        navigation = (ROOT / "_data/navigation.yml").read_text(encoding="utf-8")
        header = (ROOT / "_includes/header.html").read_text(encoding="utf-8")
        items = re.findall(
            r"^- label: (.+)\n  path: (.+)\n  nav: (.+)$",
            navigation,
            flags=re.MULTILINE,
        )
        self.assertEqual(
            items,
            [
                ("Home", "/", "home"),
                ("News", "/news/", "news"),
                ("People", "/people/", "people"),
                ("Projects", "/projects/", "projects"),
                ("Publications", "/publications/", "publications"),
                ("Contact", "/contact/", "contact"),
            ],
        )
        self.assertIn("{% for item in site.data.navigation %}", header)
        self.assertIn("{{ item.path | relative_url | escape }}", header)
        self.assertIn("{{ item.label | escape }}", header)
        self.assertNotIn("assign navigation", header)
        self.assertNotIn("<table", header.lower())

    def test_shell_has_required_accessibility_source(self):
        layout = (ROOT / "_layouts/default.html").read_text(encoding="utf-8")
        self.assertNotIn("<script", layout.lower())
        for required in [
            'name="viewport"',
            'name="description"',
            'rel="canonical"',
            'property="og:title"',
            'name="theme-color"',
            'href="#main-content"',
            '<main id="main-content"',
        ]:
            self.assertIn(required, layout)

    def test_small_ui_logo_is_current_and_used_for_ui_only(self):
        result = subprocess.run(
            [sys.executable, "scripts/build_ui_assets.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        asset = ROOT / "assets/ui/itseg-logo.webp"
        with Image.open(asset) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (296, 320))
        header = (ROOT / "_includes/header.html").read_text(encoding="utf-8")
        layout = (ROOT / "_layouts/default.html").read_text(encoding="utf-8")
        news_card = (ROOT / "_includes/news-card.html").read_text(encoding="utf-8")
        css = (ROOT / "assets/css/main.css").read_text(encoding="utf-8")
        self.assertIn("/assets/ui/itseg-logo.webp", header)
        self.assertIn('width="296" height="320"', header)
        self.assertIn("/assets/ui/itseg-logo.webp", layout)
        self.assertIn('type="image/webp"', layout)
        self.assertIn("include.item.cover == '/assets/pic/brand/logo-large.png'", news_card)
        self.assertIn('class="news-card-logo"', news_card)
        self.assertIn('alt="ITSEG logo"', news_card)
        self.assertIn("include.item.cover | relative_url | escape", news_card)
        self.assertIn(".news-card-logo", css)
        self.assertIn("object-fit: contain", css)
        self.assertIn("background: var(--cream)", css)
        self.assertNotIn("assets/ui", (ROOT / "docs/content-manifest.yml").read_text(encoding="utf-8"))

    def test_news_archive_heading_order_is_explicit(self):
        news = (ROOT / "news/index.html").read_text(encoding="utf-8")
        css = (ROOT / "assets/css/main.css").read_text(encoding="utf-8")
        self.assertIn('<h2 class="visually-hidden" id="news-archive-title">', news)
        self.assertIn('aria-labelledby="news-archive-title"', news)
        self.assertIn(".visually-hidden", css)

    def test_sitemap_discovers_public_standalone_pages(self):
        sitemap = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("site.pages | sort: 'url'", sitemap)
        self.assertIn("item.layout and item.sitemap != false", sitemap)
        self.assertIn("item.sitemap != false", sitemap)
        self.assertIn("item.published != false", sitemap)
        self.assertIn("asset_prefix == '/assets/'", sitemap)
        self.assertNotIn("index.html,news/index.html", sitemap)
        self.assertIn("sitemap: false", (ROOT / "404.html").read_text(encoding="utf-8"))

    def test_structured_metadata_uses_contextual_liquid_escaping(self):
        required_by_template = {
            "_includes/news-card.html": [
                "include.item.cover | relative_url | escape",
                "include.item.title | escape",
                "truncatewords: 28 | escape",
            ],
            "_includes/person-card.html": [
                "include.item.image | relative_url | escape",
                "include.item.title | escape",
                "include.item.role | escape",
                "include.item.affiliation | escape",
            ],
            "_includes/project-card.html": [
                "include.item.image | relative_url | escape",
                "include.item.title | escape",
                "truncatewords: 30 | escape",
            ],
            "_includes/publication-list.html": [
                "publication.id | escape",
                "publication.title | escape",
                "publication.authors | escape",
                "publication.publisher | escape",
            ],
            "_layouts/news.html": ["page.title | escape"],
            "_layouts/person.html": [
                "page.image | relative_url | escape",
                "page.title | escape",
                "page.section | escape",
                "page.role | escape",
                "page.affiliation | escape",
                "page.homepage | escape",
                "page.email and page.email != empty",
                "page.phone and page.phone != empty",
                "page.homepage and page.homepage != empty",
            ],
            "_layouts/project.html": [
                "page.image | relative_url | escape",
                "page.title | escape",
            ],
        }
        for relative, expressions in required_by_template.items():
            text = (ROOT / relative).read_text(encoding="utf-8")
            with self.subTest(relative=relative):
                for expression in expressions:
                    self.assertIn(expression, text)
        for relative in [
            "_layouts/news.html",
            "_layouts/person.html",
            "_layouts/project.html",
        ]:
            self.assertIn("{{ content }}", (ROOT / relative).read_text(encoding="utf-8"))

    def test_publication_index_uses_readable_shared_include(self):
        index = (ROOT / "publications/index.html").read_text(encoding="utf-8")
        publication_list = (ROOT / "_includes/publication-list.html").read_text(
            encoding="utf-8"
        )
        self.assertEqual(index.count("{% include publication-list.html"), 4)
        for required in [
            "include.category",
            "include.heading",
            "include.id",
            "{% for publication in records %}",
        ]:
            self.assertIn(required, publication_list)
        for text in [index, publication_list]:
            self.assertNotIn("review_status", text)
            self.assertNotIn("duplicate", text.lower())
        self.assertGreater(len(publication_list.splitlines()), 20)

    def test_public_totals_and_editorial_ordering_are_dynamic(self):
        home = (ROOT / "index.html").read_text(encoding="utf-8")
        publications = (ROOT / "publications/index.html").read_text(encoding="utf-8")
        people = (ROOT / "people/index.html").read_text(encoding="utf-8")
        projects = (ROOT / "projects/index.html").read_text(encoding="utf-8")

        self.assertIn("View all {{ site.news | size }} news items", home)
        self.assertNotIn("View all 14 news items", home)
        for variable in [
            "career_best_publications",
            "book_chapter_publications",
            "conference_publications",
            "journal_publications",
        ]:
            self.assertIn(f"{{{{ {variable} | size }}}}", publications)
        for frozen in ["(9)", "(1)", "(38)", "(68)"]:
            self.assertNotIn(frozen, publications)
        self.assertNotIn("sort: 'section_order'", people)
        self.assertNotIn("sort: 'category_order'", projects)
        self.assertEqual(people.count("sort: 'order'"), 6)
        self.assertEqual(projects.count("sort: 'order'"), 2)

    def test_editorial_review_details_are_not_rendered_publicly(self):
        public_templates = [
            "index.html",
            "people/index.html",
            "publications/index.html",
            "contact/index.html",
            "_includes/person-card.html",
            "_includes/publication-list.html",
            "_layouts/person.html",
        ]
        prohibited = re.compile(
            r"legacy source|legacy guidance|verified legacy|commented|duplicate"
            r"|editorial review|review-status|missing[^\n]*pdf|status-badge",
            flags=re.IGNORECASE,
        )
        for relative in public_templates:
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIsNone(prohibited.search(text))
        self.assertFalse((ROOT / "_includes/review-status.html").exists())

    def test_migration_records_and_internal_review_metadata_are_preserved(self):
        publications = json.loads(
            (ROOT / "_data/publications.yml").read_text(encoding="utf-8")
        )
        people = list((ROOT / "_people").glob("*.md"))
        self.assertEqual(len(publications), 116)
        self.assertEqual(len(people), 37)
        self.assertTrue(all(item.get("managed_by") == "legacy-import" for item in publications))
        for collection in ["_news", "_people", "_projects"]:
            for path in (ROOT / collection).glob("*.md"):
                self.assertIn('managed_by: "legacy-import"', path.read_text(encoding="utf-8"))
        self.assertEqual(
            sum(
                item.get("review_status") == "duplicate-preserved"
                for item in publications
            ),
            2,
        )
        people_source = "\n".join(path.read_text(encoding="utf-8") for path in people)
        self.assertEqual(people_source.count("duplicate_person: true"), 2)
        self.assertIn('source_status: "legacy-commented-public-source"', people_source)

    def test_handbooks_document_safe_editorial_workflow(self):
        editor = (ROOT / "editor-handbook.md").read_text(encoding="utf-8")
        maintainer = (ROOT / "maintainer-handbook.md").read_text(encoding="utf-8")
        combined = editor + maintainer
        for required in [
            'managed_by: "editorial"',
            'managed_by: "legacy-import"',
            "assets/uploads/news",
            "assets/uploads/people",
            "assets/uploads/projects",
            "greater than 37",
            "greater than 8",
            "publication-001` through `publication-116",
            "preserves collection files and publication rows",
            "scripts/import_legacy_content.py",
            "scripts/validate_site.py --check-source-fidelity",
            "python3 -m unittest discover -s tests -v",
        ]:
            self.assertIn(required, combined)
        for collection in ["news", "people", "projects"]:
            upload_directory = ROOT / "assets/uploads" / collection
            self.assertTrue(upload_directory.is_dir())
            self.assertNotIn(upload_directory.relative_to(ROOT), {
                Path("assets/pic/people"),
                Path("assets/pic/projects"),
                Path("assets/pic/brand"),
                Path("assets/documents"),
            })

    def test_footer_uses_canonical_external_license(self):
        footer = (ROOT / "_includes/footer.html").read_text(encoding="utf-8")
        self.assertIn(
            'href="https://github.com/ITSEG-MQ/website-itseg/blob/main/LICENSE"',
            footer,
        )
        self.assertIn('target="_blank"', footer)
        self.assertIn('rel="noopener noreferrer"', footer)
        self.assertIn(">LICENSE</a>", footer)
        self.assertNotIn("{{ '/LICENSE' | relative_url }}", footer)

    def test_robots_policy_distinguishes_production_and_staging(self):
        robots = (ROOT / "robots.txt").read_text(encoding="utf-8")
        self.assertIn('{% if site.environment == "production" %}', robots)
        self.assertIn("Allow: /", robots)
        self.assertIn("Sitemap: {{ '/sitemap.xml' | absolute_url }}", robots)
        self.assertIn("{% else %}\nDisallow: /", robots)
        self.assertLess(robots.index("Allow: /"), robots.index("{% else %}"))
        self.assertGreater(robots.index("Disallow: /"), robots.index("{% else %}"))

    def test_staging_robots_meta_is_conditionally_omitted_in_production(self):
        layout = (ROOT / "_layouts/default.html").read_text(encoding="utf-8")
        conditional = "{% if site.environment != 'production' %}"
        robots_meta = '<meta name="robots" content="noindex,nofollow">'
        self.assertIn(conditional, layout)
        self.assertIn(robots_meta, layout)
        self.assertLess(layout.index(conditional), layout.index(robots_meta))
        self.assertLess(layout.index(robots_meta), layout.index("{% endif %}", layout.index(conditional)))

    def test_workflows_pin_actions_and_serialize_production_releases(self):
        release = (ROOT / ".github/workflows/release-zip.yml").read_text(encoding="utf-8")
        validate = (ROOT / ".github/workflows/validate.yml").read_text(encoding="utf-8")
        expected = {
            "actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4": [release, validate],
            "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5": [release, validate],
            "actions/jekyll-build-pages@44a6e6beabd48582f863aeeb6cb2151cc1716697 # v1": [release, validate],
            "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4": [validate],
            "softprops/action-gh-release@efb35369e0ad2afab669f228072c1b0d510eae64 # v3.0.3": [release],
        }
        for action, workflows in expected.items():
            for workflow in workflows:
                self.assertIn(action, workflow)
        self.assertNotRegex(release + validate, r"uses:\s+[^\s]+@v\d")
        self.assertIn("concurrency:\n  group: production-release\n  cancel-in-progress: false", release)
        self.assertIn("overwrite_files: true", release)
        self.assertNotIn("replace_assets", release)
        production_config_step = "- name: Use production config"
        self.assertIn(production_config_step, validate)
        self.assertIn("cp _config_prod.yml _config.yml", validate)
        self.assertLess(validate.index(production_config_step), validate.index("actions/jekyll-build-pages@"))


if __name__ == "__main__":
    unittest.main()
