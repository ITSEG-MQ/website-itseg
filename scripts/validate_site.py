#!/usr/bin/env python3
"""Deterministic source and generated-site checks for the ITSEG Jekyll site."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from build_ui_assets import asset_errors as ui_asset_errors

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"news": 14, "people": 37, "people_source_records": 37, "projects": 8, "publications": 116}
EXPECTED_PEOPLE_SECTIONS = {
    "director": 1,
    "advisory-board": 1,
    "industry-supervisor": 1,
    "program-leaders": 12,
    "industry-engagement-officers": 16,
    "alumni-and-visit-scholars": 6,
}
EXPECTED_PEOPLE_SECTION_LABELS = {
    "director": "Director",
    "advisory-board": "Advisory Board",
    "industry-supervisor": "Industry Supervisor",
    "program-leaders": "Program Leaders",
    "industry-engagement-officers": "Industry Engagement Officers",
    "alumni-and-visit-scholars": "Alumni and Visit Scholar",
}
LIVE_PEOPLE_SECTION_LABELS = {
    "director": "Director",
    "advisory-board": "Advisory Board",
    "industry-supervisor": "Industry Supervisor",
    "program-leaders": "Program Leaders",
    "current-researchers": "Current Researchers",
    "alumni-and-visiting-scholars": "Alumni and Visiting Scholars",
}
EXPECTED_SOURCE_TITLE_BODY_COUNTS = {
    "news": {"titles": 14, "bodies": 14},
    "people": {"titles": 37, "bodies": 37},
    "projects": {"titles": 8, "bodies": 8},
    "publications": {"titles": 116, "bodies": 116},
}
SLUG_MAX_LENGTH = 64
EXPECTED_PROJECT_CATEGORIES = {"grants": 5, "other": 3}
EXPECTED_PUBLICATION_CATEGORIES = {
    "Ten Career-Best Research Outputs": 9,
    "Book Chapters": 1,
    "Fully Referred Conference Proceedings": 38,
    "Refereed Journal Articles": 68,
}
EXPECTED_FLAG_IDS = {
    "broken-recruitment-pdf",
    "missing-logo-light",
    "cloudflare-email-path",
    "duplicate-person-jiaqi-ge",
    "duplicate-publication-solguard",
    "ten-versus-nine-heading",
    "dns-broken-auckland-profile",
    "bot-blocked-external-links",
}
EXPECTED_ASSET_CATEGORIES = {"group": 36, "projects": 10, "logo": 8, "background": 4, "doc": 3}
ASSET_CATEGORY_ORDER = ("group", "projects", "logo", "background", "doc")
COLLECTION_ORDER_FIELDS = {
    "news": "source_order",
    "people": "order",
    "projects": "order",
}
MANIFEST_COLLECTION_FIELDS = {
    "news": ("legacy_id", "source_order", "permalink"),
    "people": ("category", "section", "order", "permalink"),
    "projects": ("category", "order", "permalink"),
}
EXPECTED_PDFS = {"Top-Downloaded-Article-2017-2018.pdf", "citations2.pdf", "innovation-project.pdf"}
EXPECTED_PROVENANCE_PATHS = {
    "/tmp/itseg_public_articles.json",
    "/tmp/itseg-legacy-public/html/news.html",
    "/tmp/itseg-legacy-public/html/group.html",
    "/tmp/itseg-legacy-public/html/publications.html",
    "/tmp/itseg-legacy-public/source/group.php",
    "/tmp/itseg-legacy-public/source/projects.php",
}
REQUIRED_PAGES = ["index.html", "news/index.html", "people/index.html", "projects/index.html", "publications/index.html", "contact/index.html", "404.html"]
FRONTEND_DIRS = ["_news", "_people", "_projects", "_layouts", "_includes", "assets/css", "news", "people", "projects", "publications", "contact"]
MANAGED_COLLECTION_DIRS = {
    "news": Path("_news"),
    "people": Path("_people"),
    "projects": Path("_projects"),
}
MANAGED_ASSET_DIRS = {
    Path("assets/pic/people"),
    Path("assets/pic/projects"),
    Path("assets/pic/brand"),
    Path("assets/documents"),
}
MANAGED_OUTPUT_DIRS = set(MANAGED_COLLECTION_DIRS.values()) | MANAGED_ASSET_DIRS
URL_MAP_HEADER = ("legacy_url", "new_url", "content_type", "status", "notes")
PLANNED_URL_MAP_ROWS = [
    ("/index.php", "/", "page", "migrated", "ITSEG home page implemented."),
    ("/news.php", "/news/", "collection-index", "migrated", "News index implemented with 14 records."),
    ("/group.php", "/people/", "collection-index", "migrated", "People index implemented with 37 source records."),
    ("/projects.php", "/projects/", "collection-index", "migrated", "Projects index implemented with 8 records."),
    ("/publications.php", "/publications/", "collection-index", "migrated", "Publications index implemented with 116 records."),
]
HIGH_RISK_PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "database credential file": re.compile(r"\bdbh\.php\b", re.I),
    "database connection": re.compile(r"\b(?:mysqli_connect|PDO\s*\()", re.I),
    "credential assignment": re.compile(r"\b(?:password|passwd|api[_-]?token|secret)\s*[:=]\s*['\"][^'\"]+", re.I),
    "users table query": re.compile(r"\b(?:from|into|update)\s+users\b", re.I),
}
ATTRIBUTE_NAME = re.compile(r"^[A-Za-z_:][A-Za-z0-9:._-]*$")
URL_ATTRIBUTES = {"action", "formaction", "href", "poster", "src"}
LEGACY_OWNER = "legacy-import"
EDITORIAL_OWNER = "editorial"
VALID_OWNERS = {LEGACY_OWNER, EDITORIAL_OWNER}
SAFE_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
EDITORIAL_ASSET_PREFIXES = {
    "news": "/assets/uploads/news/",
    "people": "/assets/uploads/people/",
    "projects": "/assets/uploads/projects/",
}
COLLECTION_COMMON_FIELDS = {
    "news": ("title", "date", "cover", "permalink"),
    "people": ("title", "category", "section", "image", "order", "permalink"),
    "projects": ("title", "category", "section", "image", "order", "permalink"),
}


def managed_root_errors():
    """Validate managed roots without listing or traversing an unsafe directory."""
    errors = []
    repository = ROOT.resolve()
    for relative in sorted(MANAGED_OUTPUT_DIRS, key=str):
        directory = ROOT / relative
        if directory.is_symlink():
            errors.append(f"{relative}: managed directory is a symlink")
            continue
        try:
            resolved = directory.resolve(strict=False)
        except OSError as exc:
            errors.append(f"{relative}: cannot resolve managed directory ({exc})")
            continue
        if resolved != repository and repository not in resolved.parents:
            errors.append(f"{relative}: managed directory resolves outside the repository")
        if not directory.is_dir():
            errors.append(f"{relative}: managed directory is missing or not a directory")
    return errors


def slugify(value: str, limit: int = SLUG_MAX_LENGTH) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    if len(value) <= limit:
        return value or "record"
    words = value.split("-")
    shortened = []
    length = 0
    for word in words:
        next_length = length + (1 if shortened else 0) + len(word)
        if next_length > limit:
            break
        shortened.append(word)
        length = next_length
    return "-".join(shortened) or words[0][:limit]


def unique_slug(value: str, used: set[str], suffix: str) -> str:
    candidate = slugify(value)
    if candidate not in used:
        used.add(candidate)
        return candidate
    suffix = f"-{suffix}"
    candidate = f"{slugify(value, SLUG_MAX_LENGTH - len(suffix))}{suffix}"
    counter = 2
    while candidate in used:
        numbered_suffix = f"{suffix}-{counter}"
        candidate = f"{slugify(value, SLUG_MAX_LENGTH - len(numbered_suffix))}{numbered_suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def scalar(value: str):
    value = value.strip()
    if value == "":
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        if value.lower() in {"null", "~"}:
            return None
        return value.strip("'\"")


def front_matter(path: Path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing opening front matter delimiter")
    try:
        raw, body = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError("missing closing front matter delimiter") from exc
    data = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            raise ValueError(f"unsupported front matter line: {line!r}")
        key, value = line.split(":", 1)
        data[key.strip()] = scalar(value)
    return data, body


def configured_value(name: str, config_path: Path | None = None):
    """Read a top-level scalar from the active Jekyll config without a YAML dependency."""
    path = config_path or ROOT / "_config.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(rf"^{re.escape(name)}\s*:\s*(.*?)\s*$", text, re.MULTILINE)
    return scalar(match.group(1)) if match else None


def configured_baseurl(config_path: Path | None = None) -> str:
    value = configured_value("baseurl", config_path)
    if not isinstance(value, str) or not value.strip() or value.strip() == "/":
        return ""
    return "/" + value.strip().strip("/")


def unsafe_url_reason(attribute: str, value: str) -> str | None:
    """Describe browser-active URLs that should never appear in generated attributes."""
    if value != value.strip():
        return "leading or trailing whitespace"
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return "control character"
    if "\\" in value:
        return "backslash"
    if value.startswith("//"):
        return "protocol-relative URL"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "malformed URL"
    scheme = parsed.scheme.lower()
    allowed = {"http", "https"}
    if attribute == "href":
        allowed.update({"mailto", "tel"})
    if scheme and scheme not in allowed:
        return f"unsafe scheme {scheme!r}"
    if parsed.netloc and not scheme:
        return "network-path URL"
    if scheme in {"http", "https"} and not parsed.netloc:
        return f"{scheme} URL without a host"
    if scheme in {"mailto", "tel"} and not parsed.path:
        return f"empty {scheme} URL"
    return None


class DocumentParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.images = []
        self.tags = []
        self.meta = []
        self.anchors = []
        self.ids = set()
        self.title = False
        self.errors = []

    def handle_starttag(self, tag, attrs):
        names = [name for name, _ in attrs]
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            self.errors.append(f"duplicate attributes on <{tag}>: {duplicates}")
        for name, value in attrs:
            if not ATTRIBUTE_NAME.fullmatch(name):
                self.errors.append(f"malformed attribute name {name!r} on <{tag}>")
            if value is None:
                self.errors.append(f"attribute {name!r} on <{tag}> has no value")
                continue
            if name.lower().startswith("on"):
                self.errors.append(f"unsafe event-handler attribute {name!r} on <{tag}>")
            if name.lower() in URL_ATTRIBUTES:
                reason = unsafe_url_reason(name.lower(), value)
                if reason:
                    self.errors.append(f"unsafe {name} on <{tag}> ({reason}): {value!r}")
        attrs = dict(attrs)
        self.tags.append(tag)
        if attrs.get("id"):
            self.ids.add(attrs["id"])
        if tag == "a" and attrs.get("href"):
            self.links.append(("href", attrs["href"]))
            self.anchors.append(attrs)
        if tag in {"img", "link", "script", "source"}:
            attr = "href" if tag == "link" else "src"
            if attrs.get(attr):
                self.links.append((attr, attrs[attr]))
        if tag == "img":
            self.images.append(attrs)
        if tag == "meta":
            self.meta.append(attrs)
        if tag == "title":
            self.title = True


def owner_records(records, owner):
    return [record for record in records if record[1].get("managed_by") == owner]


def safe_collection_permalink(kind: str, value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    return bool(re.fullmatch(rf"/{re.escape(kind)}/[a-z0-9]+(?:-[a-z0-9]+)*/", value))


def local_asset_error(path: Path, asset: object, prefix: str) -> str | None:
    if not isinstance(asset, str) or not asset.startswith(prefix):
        return f"asset path must start with {prefix!r}"
    relative = Path(asset.lstrip("/"))
    if asset != "/" + relative.as_posix() or relative.is_absolute() or ".." in relative.parts:
        return "asset path must be a safe root-relative path"
    if relative.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return "asset path must use a supported raster image extension"
    destination = ROOT / relative
    try:
        resolved = destination.resolve(strict=False)
        repository = ROOT.resolve()
    except OSError:
        return "asset path cannot be resolved"
    if resolved != repository and repository not in resolved.parents:
        return "asset path resolves outside the repository"
    if destination.is_symlink() or not destination.is_file():
        return f"missing regular asset {asset}"
    return None


def collection_errors(kind: str, required: list[str]):
    errors = []
    directory = ROOT / f"_{kind}"
    paths = sorted(
        path
        for path in directory.iterdir()
        if path.suffix == ".md" and not path.is_symlink() and path.is_file()
    ) if directory.is_dir() and not directory.is_symlink() else []
    records = []
    for path in paths:
        try:
            data, body = front_matter(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        records.append((path, data, body))
        owner = data.get("managed_by")
        if owner not in VALID_OWNERS:
            errors.append(
                f"{path.relative_to(ROOT)}: managed_by must be {LEGACY_OWNER!r} or {EDITORIAL_OWNER!r}"
            )
        generic_required = COLLECTION_COMMON_FIELDS[kind]
        owner_required = required if owner == LEGACY_OWNER else ["id"] if owner == EDITORIAL_OWNER else []
        for key in [*generic_required, *owner_required]:
            if key not in data or data[key] in (None, "", []):
                errors.append(f"{path.relative_to(ROOT)}: missing required field {key!r}")
            elif (key in generic_required and key != "order" or key == "id") and not isinstance(data[key], str):
                errors.append(f"{path.relative_to(ROOT)}: field {key!r} must be a string")
        if not body.strip():
            errors.append(f"{path.relative_to(ROOT)}: empty body")
        permalink = data.get("permalink")
        if permalink and not safe_collection_permalink(kind, permalink):
            errors.append(f"{path.relative_to(ROOT)}: permalink must be a safe /{kind}/lowercase-slug/ URL")
        if kind == "news" and data.get("date") and not re.match(r"^\d{4}-\d{2}-\d{2}(?:[ T].*)?$", str(data["date"])):
            errors.append(f"{path.relative_to(ROOT)}: date must begin with YYYY-MM-DD")
        if kind in {"people", "projects"} and data.get("order") is not None:
            if not isinstance(data["order"], int) or isinstance(data["order"], bool) or data["order"] < 1:
                errors.append(f"{path.relative_to(ROOT)}: order must be a positive integer")
        if kind == "people" and data.get("category") in LIVE_PEOPLE_SECTION_LABELS:
            expected_section = LIVE_PEOPLE_SECTION_LABELS[data["category"]]
            if data.get("section") != expected_section:
                errors.append(
                    f"{path.relative_to(ROOT)}: section label expected {expected_section!r}, found {data.get('section')!r}"
                )
        elif kind == "people" and data.get("category"):
            errors.append(f"{path.relative_to(ROOT)}: category is not rendered by the People page")
        if kind == "projects" and data.get("category") not in {None, "", *EXPECTED_PROJECT_CATEGORIES}:
            errors.append(f"{path.relative_to(ROOT)}: category is not rendered by the Projects page")

        asset = data.get("cover") if kind == "news" else data.get("image")
        if asset:
            if owner == EDITORIAL_OWNER:
                prefix = EDITORIAL_ASSET_PREFIXES[kind]
                if kind == "people" and str(asset).startswith("/assets/pic/people/"):
                    # Migrated portraits remain provenance-managed assets while
                    # the live people records are now editorially maintained.
                    prefix = "/assets/pic/people/"
            else:
                prefix = {
                    "news": "/assets/pic/brand/",
                    "people": "/assets/pic/people/",
                    "projects": "/assets/pic/projects/",
                }[kind]
            reason = local_asset_error(path, asset, prefix)
            if reason:
                errors.append(f"{path.relative_to(ROOT)}: {reason}")
        if owner == EDITORIAL_OWNER:
            identifier = data.get("id")
            if not isinstance(identifier, str) or not SAFE_IDENTIFIER.fullmatch(identifier):
                errors.append(f"{path.relative_to(ROOT)}: editorial id must be a lowercase hyphenated identifier")
            elif path.name != f"{identifier}.md":
                errors.append(f"{path.relative_to(ROOT)}: editorial filename must be {identifier}.md")
            expected_permalink = f"/{kind}/{identifier}/" if isinstance(identifier, str) else None
            if expected_permalink and permalink != expected_permalink:
                errors.append(
                    f"{path.relative_to(ROOT)}: editorial permalink expected {expected_permalink!r}, found {permalink!r}"
                )
    return paths, records, errors


def canonical_collection_manifest_records(kind, records):
    """Build the exact manifest list from generated records in source order."""
    order_field = COLLECTION_ORDER_FIELDS[kind]
    fields = MANIFEST_COLLECTION_FIELDS[kind]

    def order_key(item):
        path, data, _ = item
        value = data.get(order_field)
        return (not isinstance(value, int), value if isinstance(value, int) else 0, path.name)

    return [
        {
            "file": str(path.relative_to(ROOT)),
            **{field: data.get(field) for field in fields},
        }
        for path, data, _ in sorted(owner_records(records, LEGACY_OWNER), key=order_key)
    ]


def canonical_asset_records(assets):
    """Order asset records independently of their manifest list position."""
    category_rank = {category: index for index, category in enumerate(ASSET_CATEGORY_ORDER)}
    return sorted(
        (asset for asset in assets if isinstance(asset, dict)),
        key=lambda asset: (
            category_rank.get(asset.get("source_category"), len(category_rank)),
            str(asset.get("source_name", "")),
        ),
    )


def publication_errors():
    errors = []
    path = ROOT / "_data/publications.yml"
    try:
        publications = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"_data/publications.yml: must be JSON-compatible YAML ({exc})"]
    if not isinstance(publications, list):
        return [], ["_data/publications.yml: top level must be a list"]
    ids = []
    for index, pub in enumerate(publications, 1):
        if not isinstance(pub, dict):
            errors.append(f"publication {index}: must be an object")
            continue
        for key in ["managed_by", "id", "title", "authors", "publisher", "category"]:
            if not pub.get(key):
                errors.append(f"publication {index}: missing required field {key!r}")
            elif not isinstance(pub[key], str):
                errors.append(f"publication {index}: field {key!r} must be a string")
        owner = pub.get("managed_by")
        if owner not in VALID_OWNERS:
            errors.append(
                f"publication {index}: managed_by must be {LEGACY_OWNER!r} or {EDITORIAL_OWNER!r}"
            )
        identifier = pub.get("id")
        ids.append(identifier)
        if not isinstance(identifier, str) or not SAFE_IDENTIFIER.fullmatch(identifier):
            errors.append(f"publication {index}: id must be a lowercase hyphenated identifier")
        if pub.get("category") not in EXPECTED_PUBLICATION_CATEGORIES:
            errors.append(
                f"publication {index}: category is not one of the existing rendered publication categories"
            )
    comparable_ids = [identifier for identifier in ids if isinstance(identifier, str)]
    if len(comparable_ids) != len(set(comparable_ids)):
        errors.append("publications: ids are not unique")
    legacy_publications = [
        pub for pub in publications
        if isinstance(pub, dict) and pub.get("managed_by") == LEGACY_OWNER
    ]
    if len(legacy_publications) != EXPECTED["publications"]:
        errors.append(
            f"legacy publications: expected {EXPECTED['publications']}, found {len(legacy_publications)}"
        )
    categories = Counter(pub.get("category") for pub in legacy_publications)
    if dict(categories) != EXPECTED_PUBLICATION_CATEGORIES:
        errors.append(
            f"legacy publications: category counts expected {EXPECTED_PUBLICATION_CATEGORIES}, found {dict(categories)}"
        )
    source_orders = [pub.get("source_order") for pub in legacy_publications]
    if source_orders != list(range(1, EXPECTED["publications"] + 1)):
        errors.append("legacy publications: source_order must remain exactly 1 through 116 in source order")
    expected_ids = [f"publication-{index:03d}" for index in range(1, EXPECTED["publications"] + 1)]
    if [pub.get("id") for pub in legacy_publications] != expected_ids:
        errors.append("legacy publications: ids and record order must remain publication-001 through publication-116")
    solguard = [
        pub
        for pub in legacy_publications
        if pub.get("title") == "SolGuard: Preventing external call issues in smart contract-based multi-agent robotic systems"
    ]
    if len(solguard) != 2:
        errors.append(f"publications: expected two preserved SolGuard rows, found {len(solguard)}")
    elif any(
        pub.get("duplicate") is not True
        or pub.get("duplicate_group") != "solguard-external-call-issues"
        or pub.get("review_status") != "duplicate-preserved"
        for pub in solguard
    ):
        errors.append("publications: both SolGuard rows must be flagged as preserved duplicates")
    return publications, errors


def collection_semantic_errors(records):
    errors = []
    all_permalinks = []
    all_editorial_ids = []
    all_baseline_identities = set()
    for kind, found in records.items():
        all_permalinks.extend(
            (data.get("permalink"), path.relative_to(ROOT))
            for path, data, _ in found
            if data.get("permalink")
        )
        editorial = owner_records(found, EDITORIAL_OWNER)
        editorial_ids = [data.get("id") for _, data, _ in editorial]
        comparable_ids = [identifier for identifier in editorial_ids if isinstance(identifier, str)]
        all_editorial_ids.extend(comparable_ids)
        if len(comparable_ids) != len(set(comparable_ids)):
            errors.append(f"{kind}: editorial ids are not unique")
        baseline_identities = {
            identity
            for path, data, _ in owner_records(found, LEGACY_OWNER)
            for identity in (path.stem, str(data.get("legacy_id", "")))
            if identity
        }
        all_baseline_identities.update(baseline_identities)
        collisions = sorted(set(comparable_ids) & baseline_identities)
        if collisions:
            errors.append(f"{kind}: editorial ids collide with the legacy baseline: {collisions}")
    duplicate_editorial_ids = sorted(
        identifier for identifier, count in Counter(all_editorial_ids).items() if count > 1
    )
    if duplicate_editorial_ids:
        errors.append(f"collections: editorial ids are not globally unique: {duplicate_editorial_ids}")
    global_baseline_collisions = sorted(set(all_editorial_ids) & all_baseline_identities)
    if global_baseline_collisions:
        errors.append(
            f"collections: editorial ids collide with legacy baseline identities: {global_baseline_collisions}"
        )
    permalink_values = [value for value, _ in all_permalinks]
    if len(permalink_values) != len(set(permalink_values)):
        duplicates = sorted(value for value, count in Counter(permalink_values).items() if count > 1)
        errors.append(f"collections: permalinks are not unique: {duplicates}")

    news = owner_records(records.get("news", []), LEGACY_OWNER)
    if len(news) != EXPECTED["news"]:
        errors.append(f"legacy news: expected {EXPECTED['news']}, found {len(news)}")
    legacy_ids = [str(data.get("legacy_id")) for _, data, _ in news]
    expected_ids = {"80", "79", "12", "11", "10", "9", "8", "7", "6", "5", "4", "2", "1", "3"}
    if set(legacy_ids) != expected_ids or len(legacy_ids) != len(set(legacy_ids)):
        errors.append(f"news: legacy ids do not match the 14 public source records: {legacy_ids}")
    news_source_orders = [data.get("source_order") for _, data, _ in news]
    if sorted(value for value in news_source_orders if isinstance(value, int)) != list(range(1, 15)):
        errors.append("news: source_order values must be exactly 1 through 14")
    news_permalinks = []
    for path, data, _ in news:
        if not isinstance(data.get("external_urls"), list) or not isinstance(data.get("legacy_referenced_urls"), list):
            errors.append(f"{path.relative_to(ROOT)}: external URL preservation fields must be JSON arrays")
        elif data.get("legacy_referenced_urls") and data.get("external_url") != data["legacy_referenced_urls"][0]:
            errors.append(f"{path.relative_to(ROOT)}: primary external_url does not preserve the first legacy URL")
        if not str(data.get("cover", "")).startswith("/assets/pic/brand/"):
            errors.append(f"{path.relative_to(ROOT)}: news cover is outside assets/pic/brand")
        day = str(data.get("date", ""))[:10]
        expected_slug = slugify(str(data.get("title", "")))
        expected_stem = f"{day}-{data.get('legacy_id')}-{expected_slug}"
        if path.stem != expected_stem:
            errors.append(f"{path.relative_to(ROOT)}: filename does not use the complete-word {SLUG_MAX_LENGTH}-character slug")
        expected_permalink = f"/news/{expected_stem}/"
        if data.get("permalink") != expected_permalink:
            errors.append(f"{path.relative_to(ROOT)}: permalink expected {expected_permalink!r}, found {data.get('permalink')!r}")
        news_permalinks.append(data.get("permalink"))
    if len(news_permalinks) != len(set(news_permalinks)):
        errors.append("news: permalinks are not unique")

    all_people = records.get("people", [])
    if not all_people:
        errors.append("people: live collection must contain at least one record")
    if owner_records(all_people, LEGACY_OWNER):
        errors.append(
            "people: live records are editorially maintained; legacy-import records belong only to the provenance manifest"
        )
    all_people_orders = [
        data.get("order")
        for _, data, _ in all_people
        if isinstance(data.get("order"), int)
    ]
    if len(all_people_orders) != len(set(all_people_orders)):
        errors.append("people: order values must be unique")
    for path, data, body in all_people:
        if re.search(r"<p[^>]*>\s*(?:<[^>]+>\s*)*(?:Email|Phone|Homepage):", body, re.I):
            errors.append(f"{path.relative_to(ROOT)}: biography body duplicates contact/homepage front matter")
        if re.search(r"<p[^>]*>\s*<(?:b|i)\b", body, re.I):
            errors.append(f"{path.relative_to(ROOT)}: biography body duplicates role/affiliation front matter")
        homepage = data.get("homepage")
        if homepage:
            reason = unsafe_url_reason("href", str(homepage))
            if reason or urlsplit(str(homepage)).scheme.lower() not in {"http", "https"}:
                errors.append(
                    f"{path.relative_to(ROOT)}: homepage must be a safe absolute HTTP(S) URL"
                )

    all_projects = records.get("projects", [])
    projects = owner_records(all_projects, LEGACY_OWNER)
    if len(projects) != EXPECTED["projects"]:
        errors.append(f"legacy projects: expected {EXPECTED['projects']}, found {len(projects)}")
    project_categories = Counter(data.get("category") for _, data, _ in projects)
    if dict(project_categories) != EXPECTED_PROJECT_CATEGORIES:
        errors.append(f"projects: category counts expected {EXPECTED_PROJECT_CATEGORIES}, found {dict(project_categories)}")
    all_project_orders = [data.get("order") for _, data, _ in all_projects if isinstance(data.get("order"), int)]
    if len(all_project_orders) != len(set(all_project_orders)):
        errors.append("projects: order values must be unique across legacy and editorial records")
    for path, data, _ in owner_records(all_projects, EDITORIAL_OWNER):
        if isinstance(data.get("order"), int) and data["order"] <= EXPECTED["projects"]:
            errors.append(
                f"{path.relative_to(ROOT)}: editorial project order must be above the legacy range (greater than 8)"
            )
    project_permalinks = []
    used_project_slugs = set()
    for path, data, _ in sorted(projects, key=lambda record: record[1].get("order", 0)):
        if not str(data.get("image", "")).startswith("/assets/pic/projects/"):
            errors.append(f"{path.relative_to(ROOT)}: project image is outside assets/pic/projects")
        expected_slug = unique_slug(str(data.get("title", "")), used_project_slugs, f"{data.get('order', 0):02d}")
        order = data.get("order")
        if not isinstance(order, int) or path.name != f"{order:02d}-{expected_slug}.md":
            errors.append(f"{path.relative_to(ROOT)}: numbered filename does not use the complete-word slug")
        expected_permalink = f"/projects/{expected_slug}/"
        if data.get("permalink") != expected_permalink:
            errors.append(f"{path.relative_to(ROOT)}: permalink expected {expected_permalink!r}, found {data.get('permalink')!r}")
        project_permalinks.append(data.get("permalink"))
    if len(project_permalinks) != len(set(project_permalinks)):
        errors.append("projects: permalinks are not unique")
    return errors


def source_scan_errors():
    errors = ui_asset_errors()
    suffixes = {".html", ".md", ".css", ".scss", ".yml", ".yaml", ".json", ".py"}
    candidates = []
    for rel in FRONTEND_DIRS:
        path = ROOT / rel
        if path.is_file():
            candidates.append(path)
        elif path.exists():
            candidates.extend(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)
    candidates.extend(ROOT / name for name in ["index.html", "404.html", "_config.yml", "_config_prod.yml"] if (ROOT / name).is_file())
    for path in sorted(set(candidates)):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT)
        if re.search(r"(?:href|src)\s*=\s*['\"][^'\"]*\.php(?:[?#'\"]|$)", text, re.I):
            errors.append(f"{rel}: contains an internal .php link")
        if re.search(r"\bTACPS\b|tacps\.org", text, re.I):
            errors.append(f"{rel}: contains removed sample-site branding")
        for label, pattern in HIGH_RISK_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{rel}: contains possible {label}")
    php_files = [p for p in ROOT.rglob("*.php") if ".git" not in p.parts and "_site" not in p.parts]
    for path in php_files:
        errors.append(f"{path.relative_to(ROOT)}: PHP is not part of the static site")
    return errors


def candidate_targets(site: Path, page: Path, value: str, baseurl: str | None = None):
    split = urlsplit(value)
    if split.scheme or split.netloc or value.startswith(("mailto:", "tel:", "data:")):
        return []
    raw = unquote(split.path)
    if not raw:
        return []
    if raw.startswith("/"):
        relative = raw.lstrip("/")
        active_baseurl = configured_baseurl() if baseurl is None else baseurl
        baseurl_relative = active_baseurl.strip("/")
        if baseurl_relative and (
            relative == baseurl_relative or relative.startswith(baseurl_relative + "/")
        ):
            relative = relative[len(baseurl_relative):].lstrip("/")
        target = site / relative
    else:
        target = page.parent / raw
    options = [target]
    if target.suffix == "":
        options.extend([target / "index.html", target.with_suffix(".html")])
    return options


def generated_errors(site: Path, collection_records, config_path: Path | None = None):
    errors = []
    if not site.is_dir():
        return [f"generated site directory does not exist: {site}"]
    for rel in ["robots.txt", "sitemap.xml"]:
        if not (site / rel).is_file():
            errors.append(f"generated site missing {rel}")
    for rel in REQUIRED_PAGES:
        if not (site / rel).is_file():
            errors.append(f"generated site missing {rel}")
    for kind, records in collection_records.items():
        for path, data, _ in records:
            permalink = str(data.get("permalink", ""))
            if permalink:
                target = site / permalink.lstrip("/") / "index.html"
            else:
                target = site / kind / path.stem / "index.html"
            if not target.is_file():
                errors.append(f"generated site missing page for {path.relative_to(ROOT)}: {target.relative_to(site)}")
    html_paths = sorted(site.rglob("*.html"))
    if not html_paths:
        errors.append("generated site contains no HTML")
        return errors
    baseurl = configured_baseurl(config_path)
    environment = configured_value("environment", config_path)
    for path in html_paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(site)
        parser = DocumentParser()
        parser.feed(text)
        parser.close()
        errors.extend(f"{rel}: {error}" for error in parser.errors)
        if not parser.title:
            errors.append(f"{rel}: missing title element")
        if parser.tags.count("main") != 1:
            errors.append(f"{rel}: expected exactly one main landmark, found {parser.tags.count('main')}")
        if not any(anchor.get("href") == "#main-content" for anchor in parser.anchors):
            errors.append(f"{rel}: missing skip link to #main-content")
        if "main-content" not in parser.ids:
            errors.append(f"{rel}: main landmark is missing id=main-content")
        if not any(m.get("name", "").lower() == "viewport" for m in parser.meta):
            errors.append(f"{rel}: missing viewport meta")
        if not any(m.get("name", "").lower() == "description" and m.get("content") for m in parser.meta):
            errors.append(f"{rel}: missing description meta")
        if not any(m.get("name", "").lower() == "theme-color" and m.get("content") for m in parser.meta):
            errors.append(f"{rel}: missing theme-color meta")
        if not any(m.get("property", "").lower() == "og:title" for m in parser.meta):
            errors.append(f"{rel}: missing Open Graph title")
        robots = [m for m in parser.meta if m.get("name", "").lower() == "robots"]
        if environment == "production" and robots:
            errors.append(f"{rel}: production page must omit robots noindex metadata")
        if environment != "production" and not any(
            m.get("content", "").replace(" ", "").lower() == "noindex,nofollow"
            for m in robots
        ):
            errors.append(f"{rel}: staging page is missing robots noindex,nofollow metadata")
        if not re.search(r'<link\s+[^>]*rel=["\']canonical["\']', text, re.I):
            errors.append(f"{rel}: missing canonical link")
        if re.search(r"\bTACPS\b|tacps\.org", text, re.I):
            errors.append(f"{rel}: contains removed sample-site branding")
        if re.search(r"(?:href|src)=[\"'][^\"']*\.php(?:[?#\"']|$)", text, re.I):
            errors.append(f"{rel}: contains a .php link")
        if "<table" in text.lower() and "nav" in text.lower():
            errors.append(f"{rel}: possible table-based navigation")
        if "script" in parser.tags:
            errors.append(f"{rel}: JavaScript is not required by this static site")
        if "{{" in text or "{%" in text:
            errors.append(f"{rel}: contains unrendered Liquid")
        for image in parser.images:
            for attr in ["src", "alt", "width", "height"]:
                if not image.get(attr):
                    errors.append(f"{rel}: image missing {attr}")
            if image.get("class") != "site-logo" and image.get("loading") != "lazy":
                errors.append(f"{rel}: content image missing loading=lazy")
        for anchor in parser.anchors:
            if anchor.get("target", "").lower() == "_blank":
                rel_values = set(anchor.get("rel", "").lower().split())
                if not {"noopener", "noreferrer"}.issubset(rel_values):
                    errors.append(f"{rel}: target=_blank link is missing rel=noopener noreferrer")
        for attr, value in parser.links:
            if value.startswith("{{"):
                errors.append(f"{rel}: unrendered Liquid link {value}")
                continue
            targets = candidate_targets(site, path, value, baseurl)
            if targets and not any(t.exists() for t in targets):
                errors.append(f"{rel}: broken internal {attr} {value}")
    return errors


def managed_output_errors(manifest, records=None):
    """Keep legacy assets exact while allowing valid editorial collection files."""
    errors = []
    expected_by_directory = {relative: [] for relative in MANAGED_OUTPUT_DIRS}
    collections = manifest.get("collections", {}) if isinstance(manifest, dict) else {}
    for kind, relative in MANAGED_COLLECTION_DIRS.items():
        entries = collections.get(kind, []) if isinstance(collections, dict) else []
        for record in entries if isinstance(entries, list) else []:
            value = record.get("file") if isinstance(record, dict) else None
            path = Path(value) if isinstance(value, str) else None
            if path is None or path.is_absolute() or ".." in path.parts or path.parent != relative:
                errors.append(f"manifest {kind} collection has unsafe managed path: {value!r}")
                continue
            expected_by_directory[relative].append(path.name)

    assets = manifest.get("assets", []) if isinstance(manifest, dict) else []
    for record in assets if isinstance(assets, list) else []:
        value = record.get("destination") if isinstance(record, dict) else None
        path = Path(value.lstrip("/")) if isinstance(value, str) else None
        if (
            path is None
            or path.is_absolute()
            or ".." in path.parts
            or path.parent not in MANAGED_ASSET_DIRS
        ):
            errors.append(f"manifest asset has unsafe managed path: {value!r}")
            continue
        expected_by_directory[path.parent].append(path.name)

    collection_kind_by_path = {relative: kind for kind, relative in MANAGED_COLLECTION_DIRS.items()}
    for relative in sorted(MANAGED_OUTPUT_DIRS, key=str):
        expected_names = expected_by_directory[relative]
        if len(expected_names) != len(set(expected_names)):
            errors.append(f"{relative}: manifest contains duplicate managed filenames")
        directory = ROOT / relative
        actual_names = []
        for entry in directory.iterdir():
            actual_names.append(entry.name)
            if entry.is_symlink():
                errors.append(f"{entry.relative_to(ROOT)}: managed output is a symlink")
            elif not entry.is_file():
                errors.append(f"{entry.relative_to(ROOT)}: unexpected non-file entry in managed directory")
        if relative in MANAGED_ASSET_DIRS:
            if sorted(actual_names) != sorted(expected_names):
                missing = sorted(set(expected_names) - set(actual_names))
                extra = sorted(set(actual_names) - set(expected_names))
                errors.append(f"{relative}: managed files differ from exact manifest set; missing={missing}, extra={extra}")
            continue

        kind = collection_kind_by_path[relative]
        non_markdown = sorted(name for name in actual_names if Path(name).suffix != ".md")
        if non_markdown:
            errors.append(f"{relative}: unexpected non-Markdown files in collection: {non_markdown}")
        if kind == "people":
            # The manifest retains the immutable 37-record provenance baseline,
            # while the live roster is an independently edited collection.
            continue
        found = records.get(kind, []) if isinstance(records, dict) else []
        actual_legacy_names = sorted(
            path.name for path, data, _ in found if data.get("managed_by") == LEGACY_OWNER
        )
        if actual_legacy_names != sorted(expected_names):
            missing = sorted(set(expected_names) - set(actual_legacy_names))
            extra = sorted(set(actual_legacy_names) - set(expected_names))
            errors.append(
                f"{relative}: legacy-import files differ from exact manifest set; missing={missing}, extra={extra}"
            )
    return errors


def manifest_errors(records, manifest=None):
    errors = []
    if manifest is None:
        path = ROOT / "docs/content-manifest.yml"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [f"docs/content-manifest.yml: must be JSON-compatible YAML ({exc})"]
    else:
        data = manifest
    errors.extend(managed_output_errors(data, records))
    counts = data.get("counts", {}) if isinstance(data, dict) else {}
    for key, expected in EXPECTED.items():
        if counts.get(key) != expected:
            errors.append(f"manifest count {key!r}: expected {expected}, found {counts.get(key)!r}")
    if counts.get("assets") != 61:
        errors.append(f"manifest count 'assets': expected 61, found {counts.get('assets')!r}")
    if counts.get("pdfs") != 3:
        errors.append(f"manifest count 'pdfs': expected 3, found {counts.get('pdfs')!r}")
    if data.get("people_sections") != EXPECTED_PEOPLE_SECTIONS:
        errors.append(f"manifest people sections: expected {EXPECTED_PEOPLE_SECTIONS}, found {data.get('people_sections')!r}")
    if data.get("people_section_labels") != EXPECTED_PEOPLE_SECTION_LABELS:
        errors.append(
            f"manifest people section labels: expected {EXPECTED_PEOPLE_SECTION_LABELS}, "
            f"found {data.get('people_section_labels')!r}"
        )
    if data.get("source_title_body_counts") != EXPECTED_SOURCE_TITLE_BODY_COUNTS:
        errors.append(
            f"manifest source title/body counts: expected {EXPECTED_SOURCE_TITLE_BODY_COUNTS}, "
            f"found {data.get('source_title_body_counts')!r}"
        )
    if data.get("project_categories") != EXPECTED_PROJECT_CATEGORIES:
        errors.append(f"manifest project categories: expected {EXPECTED_PROJECT_CATEGORIES}, found {data.get('project_categories')!r}")
    if data.get("publication_categories") != EXPECTED_PUBLICATION_CATEGORIES:
        errors.append(
            f"manifest publication categories: expected {EXPECTED_PUBLICATION_CATEGORIES}, found {data.get('publication_categories')!r}"
        )
    flags = data.get("flags", [])
    flag_ids = {flag.get("id") for flag in flags if isinstance(flag, dict)}
    if flag_ids != EXPECTED_FLAG_IDS:
        errors.append(f"manifest flags: expected {sorted(EXPECTED_FLAG_IDS)}, found {sorted(str(item) for item in flag_ids)}")

    manifest_collections = data.get("collections", {})
    for kind in MANIFEST_COLLECTION_FIELDS:
        entries = manifest_collections.get(kind, []) if isinstance(manifest_collections, dict) else []
        expected = canonical_collection_manifest_records(kind, records.get(kind, []))
        entry_files = [record.get("file") for record in entries if isinstance(record, dict)]
        if len(entry_files) != len(set(entry_files)):
            errors.append(f"manifest {kind} collection contains duplicate file records")
        if kind == "people":
            baseline_orders = [
                record.get("order") for record in entries if isinstance(record, dict)
            ]
            if len(entries) != EXPECTED["people"] or baseline_orders != list(
                range(1, EXPECTED["people"] + 1)
            ):
                errors.append(
                    "manifest people collection is not in canonical 37-record provenance order"
                )
            continue
        if entries != expected:
            errors.append(
                f"manifest {kind} collection does not exactly match canonical generated order and required metadata"
            )

    provenance = data.get("source_provenance", [])
    provenance_paths = {
        record.get("path")
        for record in provenance
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }
    if provenance_paths != EXPECTED_PROVENANCE_PATHS or len(provenance) != len(EXPECTED_PROVENANCE_PATHS):
        errors.append(
            f"manifest source provenance paths: expected {sorted(EXPECTED_PROVENANCE_PATHS)}, "
            f"found {sorted(str(value) for value in provenance_paths)}"
        )
    for record in provenance if isinstance(provenance, list) else []:
        if not isinstance(record, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))):
            errors.append("manifest source provenance entries require SHA-256 hashes")

    assets = data.get("assets", [])
    if not isinstance(assets, list) or len(assets) != 61:
        errors.append(f"manifest assets: expected a 61-record list, found {type(assets).__name__} / {len(assets) if isinstance(assets, list) else 'n/a'}")
        assets = []
    elif assets != canonical_asset_records(assets):
        errors.append(
            "manifest assets are not in canonical source order "
            "(group, projects, logo, background, doc; then source_name)"
        )
    destinations = []
    categories = Counter()
    for asset in assets:
        if not isinstance(asset, dict):
            errors.append("manifest asset entry must be an object")
            continue
        categories[asset.get("source_category")] += 1
        destination = str(asset.get("destination", ""))
        destinations.append(destination)
        path = ROOT / destination.lstrip("/")
        if path.is_symlink():
            errors.append(f"manifest asset is a symlink: {destination}")
            continue
        if not path.is_file():
            errors.append(f"manifest asset missing from worktree: {destination}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != asset.get("destination_sha256"):
            errors.append(f"manifest asset checksum mismatch: {destination}")
        if path.stat().st_size != asset.get("destination_bytes"):
            errors.append(f"manifest asset size mismatch: {destination}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(asset.get("source_sha256", ""))):
            errors.append(f"manifest asset source checksum missing or invalid: {destination}")
    if len(destinations) != len(set(destinations)):
        errors.append("manifest assets: destination paths are not unique")
    if dict(categories) != EXPECTED_ASSET_CATEGORIES:
        errors.append(f"manifest asset categories: expected {EXPECTED_ASSET_CATEGORIES}, found {dict(categories)}")

    pdf_dir = ROOT / "assets/documents"
    pdf_names = {
        path.name
        for path in pdf_dir.iterdir()
        if path.suffix.lower() == ".pdf" and not path.is_symlink() and path.is_file()
    } if pdf_dir.is_dir() and not pdf_dir.is_symlink() else set()
    if pdf_names != EXPECTED_PDFS:
        errors.append(f"PDF assets: expected {sorted(EXPECTED_PDFS)}, found {sorted(pdf_names)}")
    for name in sorted(pdf_names):
        if not (pdf_dir / name).read_bytes().startswith(b"%PDF-"):
            errors.append(f"assets/documents/{name}: missing PDF file signature")
    return errors


def legacy_asset_url(asset):
    prefixes = {
        "group": "/img/group/",
        "projects": "/img/projects/",
        "logo": "/img/logo/",
        "background": "/img/background/",
        "doc": "/doc/",
    }
    prefix = prefixes.get(asset.get("source_category"))
    return f"{prefix}{asset.get('source_name')}" if prefix else None


def expected_url_map_rows(records, assets):
    """Build URL-map rows from canonical current records, never manifest order."""
    rows = list(PLANNED_URL_MAP_ROWS)
    for _, record, _ in sorted(
        owner_records(records.get("news", []), LEGACY_OWNER),
        key=lambda item: (
            item[1].get("source_order")
            if isinstance(item[1].get("source_order"), int)
            else sys.maxsize,
            item[0].name,
        ),
    ):
        legacy_id = str(record.get("legacy_id"))
        rows.append(
            (
                f"/post.php?id={legacy_id}",
                str(record.get("permalink")),
                "news",
                "migrated",
                f"Legacy article id {legacy_id}",
            )
        )
    for asset in canonical_asset_records(assets if isinstance(assets, list) else []):
        rows.append(
            (
                str(legacy_asset_url(asset)),
                str(asset.get("destination")),
                "asset",
                "migrated",
                str(asset.get("optimization")),
            )
        )
    return rows


def legacy_url_map_errors(records, assets, url_map=None):
    errors = []
    url_map = url_map or ROOT / "docs/legacy-url-map.csv"
    if not url_map.is_file():
        return ["docs/legacy-url-map.csv: missing"]
    try:
        with url_map.open(encoding="utf-8", newline="") as handle:
            parsed = list(csv.reader(handle, strict=True))
    except (OSError, csv.Error) as exc:
        return [f"docs/legacy-url-map.csv: cannot parse ({exc})"]
    if not parsed or tuple(parsed[0]) != URL_MAP_HEADER:
        errors.append(
            f"docs/legacy-url-map.csv: header must be exactly {list(URL_MAP_HEADER)} in that order"
        )
    actual = [tuple(row) for row in parsed[1:]] if parsed else []
    malformed = [index for index, row in enumerate(actual, 2) if len(row) != len(URL_MAP_HEADER)]
    if malformed:
        errors.append(f"docs/legacy-url-map.csv: rows with wrong column count: {malformed}")

    duplicate_rows = [row for row, count in Counter(actual).items() if count > 1]
    if duplicate_rows:
        errors.append(f"docs/legacy-url-map.csv: duplicate rows are forbidden ({len(duplicate_rows)} duplicate value(s))")
    legacy_urls = [row[0] for row in actual if len(row) == len(URL_MAP_HEADER)]
    duplicate_urls = [value for value, count in Counter(legacy_urls).items() if count > 1]
    if duplicate_urls:
        errors.append(f"docs/legacy-url-map.csv: duplicate legacy_url values are forbidden: {duplicate_urls}")

    expected = expected_url_map_rows(records, assets)
    if actual != expected:
        actual_counts = Counter(actual)
        expected_counts = Counter(expected)
        missing_count = sum((expected_counts - actual_counts).values())
        extra_count = sum((actual_counts - expected_counts).values())
        if missing_count or extra_count:
            errors.append(
                "docs/legacy-url-map.csv: rows do not exactly match the ordered manifest/current set; "
                f"missing={missing_count}, extra={extra_count}, expected={len(expected)}, found={len(actual)}"
            )
        else:
            errors.append("docs/legacy-url-map.csv: row order differs from the exact generated order")
    return errors


def migration_document_errors(records):
    errors = []
    review = ROOT / "docs/content-review.md"
    review_text = review.read_text(encoding="utf-8") if review.is_file() else ""
    if not review_text.strip():
        errors.append("docs/content-review.md: missing or empty")
    for required_text in [
        "37 supplied legacy profiles",
        "live `_people` collection is editorially maintained",
        "biography prose only",
        "requirements-legacy-migration.txt",
        "/tmp/itseg-migrate-venv/bin/python scripts/validate_site.py --check-source-fidelity",
        "authoritative full source-fidelity check",
    ]:
        if required_text not in review_text:
            errors.append(f"docs/content-review.md: missing migration guidance {required_text!r}")
    requirements = ROOT / "requirements-legacy-migration.txt"
    requirements_text = requirements.read_text(encoding="utf-8") if requirements.is_file() else ""
    for dependency in ["beautifulsoup4==4.15.0", "Pillow==12.3.0"]:
        if dependency not in requirements_text:
            errors.append(f"requirements-legacy-migration.txt: missing pinned dependency {dependency}")
    try:
        manifest = json.loads((ROOT / "docs/content-manifest.yml").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"docs/legacy-url-map.csv: cannot reconcile rows with manifest ({exc})")
        return errors
    errors.extend(legacy_url_map_errors(records, manifest.get("assets", [])))
    return errors


def source_fidelity_errors(records, publications):
    """Compare generated titles and bodies with the explicitly allowed public inputs."""
    errors = []
    try:
        import import_legacy_content as importer
    except (ImportError, ModuleNotFoundError) as exc:
        return [f"source fidelity: install requirements-legacy-migration.txt ({exc})"]

    try:
        importer.require_inputs()
    except SystemExit as exc:
        return [f"source fidelity: {exc}"]

    def compare_collection(kind, expected):
        actual = {
            path.name: (str(data.get("title", "")), body.strip())
            for path, data, body in owner_records(records.get(kind, []), LEGACY_OWNER)
        }
        if set(actual) != set(expected):
            errors.append(
                f"source fidelity {kind}: generated files differ; "
                f"expected {sorted(expected)}, found {sorted(actual)}"
            )
        for filename in sorted(set(actual) & set(expected)):
            if actual[filename][0] != expected[filename][0]:
                errors.append(f"source fidelity {kind}: title mismatch in {filename}")
            if actual[filename][1] != expected[filename][1].strip():
                errors.append(f"source fidelity {kind}: body mismatch in {filename}")

    def compare_metadata(kind, expected):
        actual = {
            path.name: data
            for path, data, _ in owner_records(records.get(kind, []), LEGACY_OWNER)
        }
        if actual != expected:
            errors.append(f"source fidelity {kind}: front matter differs from regenerated source expectations")

    news_expected = {}
    news_metadata_expected = {}
    source_news = json.loads(importer.ARTICLES.read_text(encoding="utf-8"))
    for source_order, record in enumerate(source_news, 1):
        legacy_id = str(record["a_id"])
        title = record["a_title"].strip()
        day = record["a_date"].strip()[:10]
        slug = importer.slugify(title)
        body = importer.sanitize_html_fragment(
            record["a_text"],
            remove_legacy_quote_only=True,
        )
        filename = f"{day}-{legacy_id}-{slug}.md"
        permalink = f"/news/{day}-{legacy_id}-{slug}/"
        legacy_urls = importer.extract_urls(record["a_text"])
        external_urls = [
            url
            for url in legacy_urls
            if urlsplit(url).hostname not in {None, "itseg.org", "www.itseg.org"}
        ]
        news_expected[filename] = (title, body)
        news_metadata_expected[filename] = {
            "managed_by": LEGACY_OWNER,
            "title": title,
            "date": record["a_date"].strip(),
            "legacy_id": legacy_id,
            "source_order": source_order,
            "legacy_url": f"/post.php?id={legacy_id}",
            "cover": importer.asset_destination(record["a_cover"]),
            "external_url": legacy_urls[0] if legacy_urls else None,
            "external_urls": external_urls,
            "legacy_referenced_urls": legacy_urls,
            "permalink": permalink,
            "source_status": "legacy-public-export",
        }
    compare_collection("news", news_expected)
    compare_metadata("news", news_metadata_expected)

    people_expected = {}
    people_metadata_expected = {}
    people_raw = importer.PUBLIC_SOURCE_FILES["people"].read_text(encoding="utf-8")
    people_soup = importer.uncomment_public_profiles(people_raw)
    occurrences = Counter()
    section_orders = Counter()
    for global_order, heading in enumerate(people_soup.find_all("h6"), 1):
        title = heading.get_text(" ", strip=True)
        occurrences[title] += 1
        occurrence = occurrences[title]
        card = heading.find_parent("div", class_="titem")
        image_card = card.find_previous_sibling("div", class_="titem")
        image = image_card.find("img")
        section = importer.person_section(title, occurrence)
        section_orders[section] += 1
        base_slug = importer.slugify(re.sub(r"^(?:a/prof\.|professor|dr)\s+", "", title, flags=re.I))
        if title == "Jiaqi Ge":
            base_slug += "-current" if occurrence == 1 else "-alumni"
        body = importer.clean_body(card, skip=importer.is_profile_metadata)
        filename = f"{base_slug}.md"
        people_expected[filename] = (title, body)
        role_tag = card.find("b")
        affiliation_tag = card.find("i")
        metadata = {
            "role": role_tag.get_text(" ", strip=True) if role_tag else "Member",
            "affiliation": affiliation_tag.get_text(" ", strip=True) if affiliation_tag else "",
            "email": "",
            "phone": "",
            "homepage": "",
        }
        for paragraph in card.find_all("p", recursive=False):
            value = paragraph.get_text(" ", strip=True)
            if value.lower().startswith("email:"):
                metadata["email"] = value.split(":", 1)[1].strip()
            elif value.lower().startswith("phone:"):
                metadata["phone"] = value.split(":", 1)[1].strip()
            elif value.lower().startswith("homepage:"):
                homepage_tag = paragraph.find("a", href=True)
                metadata["homepage"] = homepage_tag["href"] if homepage_tag else value.split(":", 1)[1].strip()
        source_status = "legacy-commented-public-source" if (
            title in {"A/Prof. Tianqing Zhu", "Dr Robert Abbas"}
            or (title == "Jiaqi Ge" and occurrence == 1)
        ) else "legacy-published-public-page"
        people_metadata_expected[filename] = {
            "managed_by": LEGACY_OWNER,
            "title": title,
            "role": metadata["role"],
            "category": section,
            "section": importer.SECTIONS[section],
            "image": importer.asset_destination(image["src"]),
            "affiliation": metadata["affiliation"],
            "email": metadata["email"],
            "phone": metadata["phone"],
            "homepage": metadata["homepage"],
            "order": global_order,
            "section_order": section_orders[section],
            "permalink": f"/people/{base_slug}/",
            "source_status": source_status,
            "source_records": 1,
            "duplicate_person": title == "Jiaqi Ge",
            "duplicate_key": "jiaqi-ge" if title == "Jiaqi Ge" else "",
        }
    # Live people are editorially maintained. The immutable 37-record people
    # baseline is checked against the provenance manifest below instead of
    # being compared with the live collection.

    project_expected = {}
    project_metadata_expected = {}
    project_soup = importer.BeautifulSoup(
        importer.PUBLIC_SOURCE_FILES["projects"].read_text(encoding="utf-8"), "html.parser"
    )
    used_slugs = set()
    project_order = 0
    category_orders = Counter()
    for section in project_soup.select("section.portfolio"):
        heading = section.select_one(".section-head h4")
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        category = "grants" if heading_text == "Australia National Competitive Grants" else "other"
        for mission in section.select(".mission"):
            project_order += 1
            title = mission.find("h5").get_text(" ", strip=True)
            image_column = mission.parent.find_next_sibling("div")
            image = image_column.find("img")
            category_orders[category] += 1
            slug = importer.unique_slug(title, used_slugs, f"{project_order:02d}")
            body = importer.clean_body(mission)
            filename = f"{project_order:02d}-{slug}.md"
            project_expected[filename] = (title, body)
            project_metadata_expected[filename] = {
                "managed_by": LEGACY_OWNER,
                "title": title,
                "category": category,
                "section": heading_text,
                "image": importer.asset_destination(image["src"]),
                "order": project_order,
                "category_order": category_orders[category],
                "permalink": f"/projects/{slug}/",
                "source_status": "legacy-published-public-page",
            }
    compare_collection("projects", project_expected)
    compare_metadata("projects", project_metadata_expected)

    publication_expected = []
    publication_soup = importer.BeautifulSoup(
        importer.PUBLIC_SOURCE_FILES["publications"].read_text(encoding="utf-8"), "html.parser"
    )
    category = ""
    for element in publication_soup.find_all(["h2", "div"]):
        if element.name == "h2":
            category = element.get_text(" ", strip=True)
            continue
        if "caption" not in element.get("class", []) or not element.select_one(".title"):
            continue
        title = element.select_one(".title").get_text(" ", strip=True)
        index = len(publication_expected) + 1
        duplicate = title == "SolGuard: Preventing external call issues in smart contract-based multi-agent robotic systems"
        publication_expected.append(
            {
                "managed_by": LEGACY_OWNER,
                "id": f"publication-{index:03d}",
                "title": title,
                "authors": element.select_one(".authors").get_text(" ", strip=True),
                "publisher": element.select_one(".publisher").get_text(" ", strip=True),
                "category": category,
                "source_order": index,
                "duplicate": duplicate,
                "duplicate_group": "solguard-external-call-issues" if duplicate else "",
                "review_status": "duplicate-preserved" if duplicate else "legacy-published-public-page",
            }
        )
    legacy_publications = [
        publication
        for publication in publications
        if isinstance(publication, dict) and publication.get("managed_by") == LEGACY_OWNER
    ]
    if legacy_publications != publication_expected:
        errors.append("source fidelity publications: regenerated records differ from the 116 source rows")

    try:
        manifest = json.loads((ROOT / "docs/content-manifest.yml").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return errors + [f"source fidelity manifest: cannot parse ({exc})"]

    expected_people_manifest = [
        {
            "file": f"_people/{filename}",
            **{
                field: metadata.get(field)
                for field in MANIFEST_COLLECTION_FIELDS["people"]
            },
        }
        for filename, metadata in sorted(
            people_metadata_expected.items(), key=lambda item: item[1]["order"]
        )
    ]
    actual_people_manifest = manifest.get("collections", {}).get("people", [])
    if actual_people_manifest != expected_people_manifest:
        errors.append(
            "source fidelity manifest: people provenance differs from the 37 source records"
        )

    expected_provenance = {
        str(path): importer.sha256(path)
        for path in [
            importer.ARTICLES,
            importer.RENDERED_SOURCE_FILES["news"],
            importer.RENDERED_SOURCE_FILES["people"],
            importer.PUBLIC_SOURCE_FILES["publications"],
            importer.PUBLIC_SOURCE_FILES["people"],
            importer.PUBLIC_SOURCE_FILES["projects"],
        ]
    }
    actual_provenance = {
        record.get("path"): record.get("sha256")
        for record in manifest.get("source_provenance", [])
        if isinstance(record, dict)
    }
    if actual_provenance != expected_provenance:
        errors.append("source fidelity manifest: source provenance hashes differ from the supplied public inputs")

    expected_assets = []
    for category, (source_dir, destination_dir) in importer.ASSET_SOURCES.items():
        for source in sorted(path for path in source_dir.iterdir() if path.is_file()):
            destination_bytes, optimization = importer.rendered_asset(source)
            destination = "/" + str((destination_dir / source.name).relative_to(ROOT))
            expected_assets.append(
                {
                    "source_category": category,
                    "source_name": source.name,
                    "destination": destination,
                    "source_bytes": source.stat().st_size,
                    "destination_bytes": len(destination_bytes),
                    "source_sha256": importer.sha256(source),
                    "destination_sha256": hashlib.sha256(destination_bytes).hexdigest(),
                    "optimization": optimization,
                }
            )
    actual_assets = manifest.get("assets", [])
    if actual_assets != expected_assets:
        errors.append(
            "source fidelity assets: ordered source hashes or deterministic regenerated asset expectations differ"
        )

    actual_counts = {
        "news": {"titles": len(news_expected), "bodies": sum(bool(body.strip()) for _, body in news_expected.values())},
        "people": {"titles": len(people_expected), "bodies": sum(bool(body.strip()) for _, body in people_expected.values())},
        "projects": {"titles": len(project_expected), "bodies": sum(bool(body.strip()) for _, body in project_expected.values())},
        "publications": {"titles": len(publication_expected), "bodies": len(publication_expected)},
    }
    if actual_counts != EXPECTED_SOURCE_TITLE_BODY_COUNTS:
        errors.append(
            f"source fidelity title/body counts: expected {EXPECTED_SOURCE_TITLE_BODY_COUNTS}, found {actual_counts}"
        )
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, help="also validate a generated _site directory")
    parser.add_argument(
        "--config",
        type=Path,
        help="Jekyll config used for generated-site baseurl/environment checks",
    )
    parser.add_argument(
        "--check-source-fidelity",
        action="store_true",
        help="compare generated titles and bodies with the safe public /tmp inputs (requires BeautifulSoup)",
    )
    args = parser.parse_args()
    root_errors = managed_root_errors()
    if root_errors:
        print(f"FAIL: {len(root_errors)} unsafe managed output root error(s)")
        for error in root_errors:
            print(f" - {error}")
        return 1
    fidelity_command = (
        "/tmp/itseg-migrate-venv/bin/python scripts/validate_site.py --check-source-fidelity"
    )
    if not args.check_source_fidelity:
        print(f"INFO: authoritative full source-fidelity check: {fidelity_command}")
    migration_errors = []
    records = {}
    specifications = {
        "news": ["title", "date", "legacy_id", "source_order", "cover", "permalink", "source_status"],
        "people": ["title", "role", "category", "section", "image", "order", "permalink", "source_status", "source_records"],
        "projects": ["title", "category", "image", "order", "permalink", "source_status"],
    }
    for kind, required in specifications.items():
        _, found, found_errors = collection_errors(kind, required)
        records[kind] = found
        migration_errors.extend(found_errors)
    publications, pub_errors = publication_errors()
    migration_errors.extend(pub_errors)
    migration_errors.extend(collection_semantic_errors(records))
    migration_errors.extend(manifest_errors(records))
    migration_errors.extend(migration_document_errors(records))
    if args.check_source_fidelity:
        migration_errors.extend(source_fidelity_errors(records, publications))
    global_errors = source_scan_errors()
    if args.site:
        config_path = args.config.resolve() if args.config else None
        global_errors.extend(generated_errors(args.site.resolve(), records, config_path))
    if migration_errors:
        print(f"FAIL: {len(migration_errors)} legacy public migration error(s)")
        for error in migration_errors:
            print(f" - {error}")
        return 1
    print("PASS: legacy public migration checks")
    if args.check_source_fidelity:
        print(" - authoritative full source-fidelity check: passed")
    for kind in ["news", "people", "projects"]:
        legacy_count = len(owner_records(records[kind], LEGACY_OWNER))
        editorial_count = len(owner_records(records[kind], EDITORIAL_OWNER))
        print(f" - {kind}: {legacy_count} legacy baseline / {editorial_count} editorial")
    legacy_publication_count = sum(
        publication.get("managed_by") == LEGACY_OWNER
        for publication in publications
        if isinstance(publication, dict)
    )
    editorial_publication_count = sum(
        publication.get("managed_by") == EDITORIAL_OWNER
        for publication in publications
        if isinstance(publication, dict)
    )
    print(
        f" - publications: {legacy_publication_count} legacy baseline / "
        f"{editorial_publication_count} editorial"
    )
    if args.site:
        print(f" - generated HTML pages: {len(list(args.site.resolve().rglob('*.html')))}")
    if global_errors:
        print(f"FAIL: {len(global_errors)} global site error(s) outside the legacy-public migration scope")
        for error in global_errors:
            print(f" - {error}")
        return 1
    print("PASS: ITSEG site validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
