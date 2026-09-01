import json
import re
import unittest
from pathlib import Path


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
        self.assertIn("{{ item.path | relative_url }}", header)
        self.assertIn("{{ item.label }}", header)
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


if __name__ == "__main__":
    unittest.main()
