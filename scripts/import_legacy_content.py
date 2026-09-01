#!/usr/bin/env python3
"""Import the supplied public ITSEG snapshot into Jekyll content collections.

The importer only reads the explicitly supplied public article export, rendered
public pages, public page sources, and the five public asset directories. It
does not inspect any other legacy files.
"""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import PIL
from bs4 import BeautifulSoup, Comment, NavigableString
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
LEGACY = Path("/tmp/itseg-legacy-public")
ARTICLES = Path("/tmp/itseg_public_articles.json")

PUBLIC_SOURCE_FILES = {
    "people": LEGACY / "source/group.php",
    "projects": LEGACY / "source/projects.php",
    "publications": LEGACY / "html/publications.html",
}
RENDERED_SOURCE_FILES = {
    "news": LEGACY / "html/news.html",
    "people": LEGACY / "html/group.html",
}
ASSET_SOURCES = {
    "group": (LEGACY / "assets/group", ROOT / "assets/pic/people"),
    "projects": (LEGACY / "assets/projects", ROOT / "assets/pic/projects"),
    "logo": (LEGACY / "assets/logo", ROOT / "assets/pic/brand"),
    "background": (LEGACY / "assets/background", ROOT / "assets/pic/brand"),
    "doc": (LEGACY / "assets/doc", ROOT / "assets/documents"),
}
ASSET_CATEGORY_ORDER = tuple(ASSET_SOURCES)
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
EXPECTED_ASSET_COUNTS = {"group": 36, "projects": 10, "logo": 8, "background": 4, "doc": 3}
PILLOW_VERSION = "12.3.0"
SAFE_BODY_TAGS = {"p", "br", "a", "strong", "b", "em", "i", "ul", "ol", "li", "blockquote"}
DROP_WITH_CONTENT_TAGS = {
    "script",
    "style",
    "iframe",
    "object",
    "embed",
    "form",
    "noscript",
    "template",
}
MANAGED_COLLECTION_DIRS = {
    Path("_news"),
    Path("_people"),
    Path("_projects"),
}
MANAGED_ASSET_DESTINATION_DIRS = {
    Path("assets/pic/people"),
    Path("assets/pic/projects"),
    Path("assets/pic/brand"),
    Path("assets/documents"),
}
MANAGED_OUTPUT_DIRS = MANAGED_COLLECTION_DIRS | MANAGED_ASSET_DESTINATION_DIRS
LEGACY_OWNER = "legacy-import"
EDITORIAL_OWNER = "editorial"

SECTIONS = {
    "director": "Director",
    "advisory-board": "Advisory Board",
    "industry-supervisor": "Industry Supervisor",
    "program-leaders": "Program Leaders",
    "industry-engagement-officers": "Industry Engagement Officers",
    "alumni-and-visit-scholars": "Alumni and Visit Scholar",
}
EXPECTED_SECTION_COUNTS = {
    "director": 1,
    "advisory-board": 1,
    "industry-supervisor": 1,
    "program-leaders": 12,
    "industry-engagement-officers": 16,
    "alumni-and-visit-scholars": 6,
}
SLUG_MAX_LENGTH = 64
PROGRAM_LEADERS = {
    "Professor Jian Yang",
    "Dr Yipeng Zhou",
    "Dr Yimeng Feng",
    "Dr Alireza Jolfaei",
    "Dr Xuyun Zhang",
    "A/Prof. Tianqing Zhu",
    "A/Prof. Xiao Liu",
    "Dr Sheng Wen",
    "A/Prof. Tianyi Zhang",
    "Dr Huai Liu",
    "Dr Xiwei Xu",
    "A/Prof. Jiong Jin",
}
CURRENT_MEMBERS = {
    "Dr Robert Abbas",
    "Yao Deng",
    "Yupeng Jiang",
    "Jiwei Guan",
    "Chuxuan Tong",
    "Yuzhe Tian",
    "Yi He",
    "Linfeng Liang",
    "Jiaohong Yao",
    "Siwei Luo",
    "Wenyu Dong",
    "Qiong Li",
    "Zhen Lu",
    "Bingbing Zhu",
    "Shuaiyi Sun",
}
ALUMNI = {"Jianchao Lu", "Yuxuan Cai", "Guannan Lou", "Samundra Deep", "Yong Li"}


def require_inputs() -> None:
    if PIL.__version__ != PILLOW_VERSION:
        raise SystemExit(
            f"Pillow {PILLOW_VERSION} is required for deterministic assets; found {PIL.__version__}"
        )
    required = [ARTICLES, *PUBLIC_SOURCE_FILES.values(), *RENDERED_SOURCE_FILES.values()]
    for source_dir, _ in ASSET_SOURCES.values():
        required.append(source_dir)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing required public source input(s): " + ", ".join(missing))
    for category, (source_dir, _) in ASSET_SOURCES.items():
        count = sum(1 for path in source_dir.iterdir() if path.is_file())
        if count != EXPECTED_ASSET_COUNTS[category]:
            raise SystemExit(f"{source_dir}: expected {EXPECTED_ASSET_COUNTS[category]} files, found {count}")


def managed_root_errors() -> list[str]:
    """Return safety errors without traversing any managed output directory."""
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
        if directory.exists() and not directory.is_dir():
            errors.append(f"{relative}: managed path is not a directory")
    return errors


def prepare_managed_roots() -> None:
    errors = managed_root_errors()
    if errors:
        raise SystemExit("Refusing to operate on unsafe managed output roots: " + "; ".join(errors))
    for relative in sorted(MANAGED_OUTPUT_DIRS, key=str):
        (ROOT / relative).mkdir(parents=True, exist_ok=True)
    errors = managed_root_errors()
    if errors:
        raise SystemExit("Refusing to operate on unsafe managed output roots: " + "; ".join(errors))


def load_previous_manifest() -> dict:
    """Load the immutable legacy baseline before regenerating it."""
    path = ROOT / "docs/content-manifest.yml"
    if not path.exists():
        return {}
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{path}: cannot read previous legacy manifest ({exc})") from exc
    if not isinstance(manifest, dict):
        raise SystemExit(f"{path}: previous legacy manifest must be an object")
    return manifest


def manifested_legacy_paths(manifest: dict) -> set[str]:
    """Return safe direct output paths owned by a legacy baseline manifest."""
    paths: set[str] = set()
    collections = manifest.get("collections", {}) if isinstance(manifest, dict) else {}
    for kind in ("news", "people", "projects"):
        relative = Path(f"_{kind}")
        entries = collections.get(kind, []) if isinstance(collections, dict) else []
        for record in entries if isinstance(entries, list) else []:
            value = record.get("file") if isinstance(record, dict) else None
            path = Path(value) if isinstance(value, str) else None
            if path is None or path.is_absolute() or ".." in path.parts or path.parent != relative:
                raise SystemExit(f"manifest {kind} collection has unsafe managed path: {value!r}")
            paths.add(str(path))
    assets = manifest.get("assets", []) if isinstance(manifest, dict) else []
    for record in assets if isinstance(assets, list) else []:
        value = record.get("destination") if isinstance(record, dict) else None
        path = Path(value.lstrip("/")) if isinstance(value, str) else None
        if (
            path is None
            or path.is_absolute()
            or ".." in path.parts
            or path.parent not in MANAGED_ASSET_DESTINATION_DIRS
        ):
            raise SystemExit(f"manifest asset has unsafe managed path: {value!r}")
        paths.add(str(path))
    return paths


def remove_stale_legacy_outputs(previous: set[str], current: set[str]) -> None:
    """Unlink only stale files recorded in the previous legacy manifest."""
    errors = managed_root_errors()
    if errors:
        raise SystemExit("Refusing to clean unsafe managed output roots: " + "; ".join(errors))
    for value in sorted(previous - current):
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or path.parent not in MANAGED_OUTPUT_DIRS:
            raise SystemExit(f"Refusing to clean unsafe manifested output path: {value!r}")
        destination = ROOT / path
        if path.parent in MANAGED_COLLECTION_DIRS and destination.is_file() and not destination.is_symlink():
            text = destination.read_text(encoding="utf-8", errors="replace")
            if text.startswith("---\n"):
                raw = text[4:].split("\n---\n", 1)[0]
                owner_line = next(
                    (line for line in raw.splitlines() if line.startswith("managed_by:")),
                    "",
                )
                if owner_line:
                    try:
                        owner = json.loads(owner_line.split(":", 1)[1].strip())
                    except json.JSONDecodeError:
                        owner = None
                    if owner == EDITORIAL_OWNER:
                        continue
        if destination.is_symlink() or destination.is_file():
            destination.unlink()


def slugify(value: str, limit: int = SLUG_MAX_LENGTH) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    if len(value) <= limit:
        return value or "record"
    words = value.split("-")
    shortened: list[str] = []
    length = 0
    for word in words:
        next_length = length + (1 if shortened else 0) + len(word)
        if next_length > limit:
            break
        shortened.append(word)
        length = next_length
    # Source titles contain no individual words this long. Keep the fallback
    # deterministic for unexpected input while enforcing the URL length cap.
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


def json_scalar(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_markdown(path: Path, fields: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    front_matter = "\n".join(f"{key}: {json_scalar(value)}" for key, value in fields.items())
    path.write_text(f"---\n{front_matter}\n---\n\n{body.strip()}\n", encoding="utf-8")


def sanitized_href(value: object) -> str | None:
    """Return a safe, normalized href or None when the link must be unwrapped."""
    href = html.unescape(str(value)).strip()
    if not href or any(ord(character) < 32 or ord(character) == 127 for character in href):
        return None
    if "\\" in href:
        return None
    parsed = urlsplit(href)
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()

    internal_publications = (
        scheme in {"http", "https"}
        and hostname in {"itseg.org", "www.itseg.org"}
        and parsed.path.rstrip("/").lower() == "/publications.php"
    ) or (
        not scheme
        and not parsed.netloc
        and parsed.path.lower() in {"publications.php", "/publications.php", "./publications.php"}
    )
    if internal_publications:
        relative_url = "{{ '/publications/' | relative_url }}"
        return relative_url + (f"#{parsed.fragment}" if parsed.fragment else "")

    if scheme in {"http", "https"}:
        return href if parsed.netloc else None
    if scheme == "mailto":
        return href if parsed.path else None
    if scheme or parsed.netloc or href.startswith("//"):
        return None
    return href


def _quote_only(value: str) -> bool:
    return bool(re.fullmatch(r"[\s\"'“”‘’`´]+", value))


def sanitize_html_fragment(fragment: str, *, remove_legacy_quote_only: bool = False) -> str:
    """Deterministically reduce an imported body fragment to the safe semantic subset."""
    soup = BeautifulSoup(fragment, "html.parser")
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        name = tag.name.lower()
        if name in DROP_WITH_CONTENT_TAGS:
            tag.decompose()
            continue
        if name not in SAFE_BODY_TAGS:
            tag.unwrap()
            continue
        if name == "a":
            href = sanitized_href(tag.get("href", ""))
            if href is None:
                tag.unwrap()
                continue
            tag.attrs = {"href": href}
        else:
            tag.attrs = {}

    for paragraph in list(soup.find_all("p")):
        text = paragraph.get_text(" ", strip=True)
        if not text:
            paragraph.decompose()
        elif remove_legacy_quote_only and _quote_only(text):
            paragraph.decompose()
    if remove_legacy_quote_only:
        for child in list(soup.contents):
            if isinstance(child, NavigableString) and _quote_only(str(child)):
                child.extract()

    pieces = []
    for child in soup.contents:
        rendered = str(child).strip()
        if rendered:
            pieces.append(rendered)
    return "\n\n".join(pieces)


def clean_body(container, skip=None) -> str:
    fragments = []
    for original in container.find_all(["p", "ul", "ol", "blockquote"], recursive=False):
        if skip is not None and skip(original):
            continue
        fragments.append(str(original))
    return sanitize_html_fragment("\n".join(fragments))


def is_profile_metadata(paragraph) -> bool:
    text = paragraph.get_text(" ", strip=True).lower()
    return (
        paragraph.find("b") is not None
        or paragraph.find("i") is not None
        or text.startswith(("email:", "phone:", "homepage:"))
    )


def asset_destination(legacy_path: str) -> str:
    name = Path(legacy_path).name
    if "/group/" in legacy_path:
        return f"/assets/pic/people/{name}"
    if "/projects/" in legacy_path:
        return f"/assets/pic/projects/{name}"
    return f"/assets/pic/brand/{name}"


def extract_urls(fragment: str) -> list[str]:
    soup = BeautifulSoup(fragment, "html.parser")
    urls = [html.unescape(a["href"]) for a in soup.find_all("a", href=True)]
    plain = re.findall(r"https?://[^\s<>\"']+", html.unescape(fragment))
    for url in plain:
        url = url.rstrip(".,;:)")
        if url not in urls:
            urls.append(url)
    return urls


def import_news() -> list[dict]:
    records = json.loads(ARTICLES.read_text(encoding="utf-8"))
    if len(records) != 14:
        raise SystemExit(f"{ARTICLES}: expected 14 article records, found {len(records)}")
    output = []
    for source_order, record in enumerate(records, 1):
        legacy_id = str(record["a_id"])
        title = record["a_title"].strip()
        timestamp = record["a_date"].strip()
        day = timestamp[:10]
        slug = slugify(title)
        permalink = f"/news/{day}-{legacy_id}-{slug}/"
        filename = f"{day}-{legacy_id}-{slug}.md"
        legacy_urls = extract_urls(record["a_text"])
        external_urls = [
            url
            for url in legacy_urls
            if urlsplit(url).hostname not in {None, "itseg.org", "www.itseg.org"}
        ]
        body = sanitize_html_fragment(
            record["a_text"],
            remove_legacy_quote_only=True,
        )
        fields = {
            "managed_by": LEGACY_OWNER,
            "title": title,
            "date": timestamp,
            "legacy_id": legacy_id,
            "source_order": source_order,
            "legacy_url": f"/post.php?id={legacy_id}",
            "cover": asset_destination(record["a_cover"]),
            "external_url": legacy_urls[0] if legacy_urls else None,
            "external_urls": external_urls,
            "legacy_referenced_urls": legacy_urls,
            "permalink": permalink,
            "source_status": "legacy-public-export",
        }
        write_markdown(ROOT / "_news" / filename, fields, body)
        output.append({"file": f"_news/{filename}", **fields})
    return output


def canonical_collection_records(kind: str, records: list[dict]) -> list[dict]:
    """Return manifest collection entries in their authoritative source order."""
    order_field = COLLECTION_ORDER_FIELDS[kind]
    fields = MANIFEST_COLLECTION_FIELDS[kind]
    return [
        {"file": record["file"], **{field: record[field] for field in fields}}
        for record in sorted(records, key=lambda record: record[order_field])
    ]


def canonical_asset_records(assets: list[dict]) -> list[dict]:
    """Return assets in importer source-category and source-filename order."""
    category_rank = {category: index for index, category in enumerate(ASSET_CATEGORY_ORDER)}
    return sorted(
        assets,
        key=lambda asset: (category_rank[asset["source_category"]], asset["source_name"]),
    )


def uncomment_public_profiles(raw: str) -> BeautifulSoup:
    # Three profiles are deliberately preserved from public source comments;
    # activating HTML comments lets the same parser handle all 37 source rows.
    expanded = re.sub(r"<!--(.*?)-->", lambda match: match.group(1), raw, flags=re.S)
    return BeautifulSoup(expanded, "html.parser")


def person_section(title: str, occurrence: int) -> str:
    if title == "A/Prof. James Xi Zheng":
        return "director"
    if title == "Dr Lei Pan":
        return "advisory-board"
    if title == "Dr Mengshi Zhang":
        return "industry-supervisor"
    if title in PROGRAM_LEADERS:
        return "program-leaders"
    if title in CURRENT_MEMBERS or (title == "Jiaqi Ge" and occurrence == 1):
        return "industry-engagement-officers"
    if title in ALUMNI or (title == "Jiaqi Ge" and occurrence == 2):
        return "alumni-and-visit-scholars"
    raise ValueError(f"Unmapped public profile: {title!r} occurrence {occurrence}")


def import_people(*, write_output: bool = True) -> list[dict]:
    """Parse the immutable 37-record people baseline.

    The live ``_people`` collection is editorially maintained. Normal importer
    runs therefore set ``write_output=False`` and use these records only for
    provenance, manifest, and source-fidelity accounting.
    """
    raw = PUBLIC_SOURCE_FILES["people"].read_text(encoding="utf-8")
    soup = uncomment_public_profiles(raw)
    headings = soup.find_all("h6")
    if len(headings) != 37:
        raise SystemExit(f"people source: expected 37 profile rows including comments, found {len(headings)}")
    occurrences: Counter[str] = Counter()
    section_orders: Counter[str] = Counter()
    output = []
    for global_order, heading in enumerate(headings, 1):
        title = heading.get_text(" ", strip=True)
        occurrences[title] += 1
        occurrence = occurrences[title]
        section = person_section(title, occurrence)
        section_orders[section] += 1
        card = heading.find_parent("div", class_="titem")
        image_card = card.find_previous_sibling("div", class_="titem") if card else None
        image = image_card.find("img") if image_card else None
        if card is None or image is None:
            raise SystemExit(f"people source: could not pair profile text/image for {title}")
        role_tag = card.find("b")
        role = role_tag.get_text(" ", strip=True) if role_tag else "Member"
        affiliation_tag = card.find("i")
        affiliation = affiliation_tag.get_text(" ", strip=True) if affiliation_tag else ""
        homepage = ""
        email = ""
        phone = ""
        for paragraph in card.find_all("p", recursive=False):
            value = paragraph.get_text(" ", strip=True)
            if value.lower().startswith("email:"):
                email = value.split(":", 1)[1].strip()
            elif value.lower().startswith("phone:"):
                phone = value.split(":", 1)[1].strip()
            elif value.lower().startswith("homepage:"):
                homepage_tag = paragraph.find("a", href=True)
                homepage = homepage_tag["href"] if homepage_tag else value.split(":", 1)[1].strip()
        base_slug = slugify(re.sub(r"^(?:a/prof\.|professor|dr)\s+", "", title, flags=re.I))
        if title == "Jiaqi Ge":
            base_slug += "-current" if occurrence == 1 else "-alumni"
        filename = f"{base_slug}.md"
        permalink = f"/people/{base_slug}/"
        source_status = "legacy-commented-public-source" if (
            title in {"A/Prof. Tianqing Zhu", "Dr Robert Abbas"}
            or (title == "Jiaqi Ge" and occurrence == 1)
        ) else "legacy-published-public-page"
        fields = {
            "managed_by": LEGACY_OWNER,
            "title": title,
            "role": role,
            "category": section,
            "section": SECTIONS[section],
            "image": asset_destination(image["src"]),
            "affiliation": affiliation,
            "email": email,
            "phone": phone,
            "homepage": homepage,
            "order": global_order,
            "section_order": section_orders[section],
            "permalink": permalink,
            "source_status": source_status,
            "source_records": 1,
            "duplicate_person": title == "Jiaqi Ge",
            "duplicate_key": "jiaqi-ge" if title == "Jiaqi Ge" else "",
        }
        body = clean_body(card, skip=is_profile_metadata)
        if write_output:
            write_markdown(ROOT / "_people" / filename, fields, body)
        output.append({"file": f"_people/{filename}", **fields})
    actual = Counter(record["category"] for record in output)
    if dict(actual) != EXPECTED_SECTION_COUNTS:
        raise SystemExit(f"people sections: expected {EXPECTED_SECTION_COUNTS}, found {dict(actual)}")
    return output


def import_projects() -> list[dict]:
    soup = BeautifulSoup(PUBLIC_SOURCE_FILES["projects"].read_text(encoding="utf-8"), "html.parser")
    output = []
    category_orders: Counter[str] = Counter()
    used_slugs: set[str] = set()
    for section in soup.select("section.portfolio"):
        heading = section.select_one(".section-head h4")
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        category = "grants" if heading_text == "Australia National Competitive Grants" else "other"
        for mission in section.select(".mission"):
            title_tag = mission.find("h5")
            image_column = mission.parent.find_next_sibling("div")
            image = image_column.find("img") if image_column else None
            if title_tag is None or image is None:
                raise SystemExit("projects source: could not pair a project title/image")
            title = title_tag.get_text(" ", strip=True)
            category_orders[category] += 1
            global_order = len(output) + 1
            slug = unique_slug(title, used_slugs, f"{global_order:02d}")
            filename = f"{global_order:02d}-{slug}.md"
            permalink = f"/projects/{slug}/"
            fields = {
                "managed_by": LEGACY_OWNER,
                "title": title,
                "category": category,
                "section": heading_text,
                "image": asset_destination(image["src"]),
                "order": global_order,
                "category_order": category_orders[category],
                "permalink": permalink,
                "source_status": "legacy-published-public-page",
            }
            body = clean_body(mission)
            write_markdown(ROOT / "_projects" / filename, fields, body)
            output.append({"file": f"_projects/{filename}", **fields})
    counts = Counter(record["category"] for record in output)
    if counts != Counter({"grants": 5, "other": 3}):
        raise SystemExit(f"project categories: expected 5 grants / 3 other, found {dict(counts)}")
    return output


def import_publications() -> list[dict]:
    destination = ROOT / "_data/publications.yml"
    editorial_records = []
    if destination.exists():
        try:
            current_records = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"{destination}: refusing to overwrite unreadable publication data ({exc})") from exc
        if not isinstance(current_records, list):
            raise SystemExit(f"{destination}: refusing to overwrite publication data that is not a list")
        editorial_records = [
            record
            for record in current_records
            if isinstance(record, dict) and record.get("managed_by") == EDITORIAL_OWNER
        ]

    soup = BeautifulSoup(PUBLIC_SOURCE_FILES["publications"].read_text(encoding="utf-8"), "html.parser")
    category = ""
    records = []
    for element in soup.find_all(["h2", "div"]):
        if element.name == "h2":
            category = element.get_text(" ", strip=True)
            continue
        if "caption" not in element.get("class", []) or not element.select_one(".title"):
            continue
        title = element.select_one(".title").get_text(" ", strip=True)
        authors = element.select_one(".authors").get_text(" ", strip=True)
        publisher = element.select_one(".publisher").get_text(" ", strip=True)
        index = len(records) + 1
        duplicate = title == "SolGuard: Preventing external call issues in smart contract-based multi-agent robotic systems"
        record = {
            "managed_by": LEGACY_OWNER,
            "id": f"publication-{index:03d}",
            "title": title,
            "authors": authors,
            "publisher": publisher,
            "category": category,
            "source_order": index,
            "duplicate": duplicate,
            "duplicate_group": "solguard-external-call-issues" if duplicate else "",
            "review_status": "duplicate-preserved" if duplicate else "legacy-published-public-page",
        }
        records.append(record)
    expected = {
        "Ten Career-Best Research Outputs": 9,
        "Book Chapters": 1,
        "Fully Referred Conference Proceedings": 38,
        "Refereed Journal Articles": 68,
    }
    counts = Counter(record["category"] for record in records)
    if len(records) != 116 or dict(counts) != expected:
        raise SystemExit(f"publications: expected 116 and {expected}, found {len(records)} and {dict(counts)}")
    if sum(1 for record in records if record["duplicate"]) != 2:
        raise SystemExit("publications: expected exactly two preserved SolGuard duplicate rows")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        destination.unlink()
    destination.write_text(
        json.dumps([*records, *editorial_records], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return records


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rendered_asset(source: Path) -> tuple[bytes, str]:
    source_bytes = source.read_bytes()
    if source.suffix.lower() not in {".jpg", ".jpeg"} or len(source_bytes) <= 1_000_000:
        return source_bytes, "copied-original"

    with Image.open(io.BytesIO(source_bytes)) as opened:
        image = ImageOps.exif_transpose(opened)
        image.load()
        if image.mode != "RGB":
            image = image.convert("RGB")
        longest = max(image.size)
        if longest > 2000:
            scale = 2000 / longest
            size = tuple(max(1, int(dimension * scale + 0.5)) for dimension in image.size)
            image = image.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0)
        output = io.BytesIO()
        image.save(
            output,
            format="JPEG",
            quality=85,
            subsampling=2,
            optimize=False,
            progressive=False,
            exif=b"",
        )
    return output.getvalue(), "pillow-12.3.0-jpeg-q85-max-2000"


def copy_assets() -> list[dict]:
    records = []
    for category, (source_dir, destination_dir) in ASSET_SOURCES.items():
        destination_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(path for path in source_dir.iterdir() if path.is_file()):
            destination = destination_dir / source.name
            if destination.is_symlink():
                destination.unlink()
            destination_bytes, optimization = rendered_asset(source)
            destination.write_bytes(destination_bytes)
            records.append(
                {
                    "source_category": category,
                    "source_name": source.name,
                    "destination": "/" + str(destination.relative_to(ROOT)),
                    "source_bytes": source.stat().st_size,
                    "destination_bytes": destination.stat().st_size,
                    "source_sha256": sha256(source),
                    "destination_sha256": sha256(destination),
                    "optimization": optimization,
                }
            )
    if len(records) != 61:
        raise SystemExit(f"assets: expected 61 copied public assets, found {len(records)}")
    return records


def legacy_asset_url(asset: dict) -> str:
    category = asset["source_category"]
    name = asset["source_name"]
    if category == "group":
        return f"/img/group/{name}"
    if category == "projects":
        return f"/img/projects/{name}"
    if category == "logo":
        return f"/img/logo/{name}"
    if category == "background":
        return f"/img/background/{name}"
    return f"/doc/{name}"


def write_url_map(news: list[dict], assets: list[dict]) -> None:
    destination = ROOT / "docs/legacy-url-map.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        ("/index.php", "/", "page", "migrated", "ITSEG home page implemented."),
        ("/news.php", "/news/", "collection-index", "migrated", "News index implemented with 14 records."),
        ("/group.php", "/people/", "collection-index", "migrated", "People index implemented with 37 source records."),
        ("/projects.php", "/projects/", "collection-index", "migrated", "Projects index implemented with 8 records."),
        ("/publications.php", "/publications/", "collection-index", "migrated", "Publications index implemented with 116 records."),
    ]
    rows.extend(
        (record["legacy_url"], record["permalink"], "news", "migrated", f"Legacy article id {record['legacy_id']}")
        for record in sorted(news, key=lambda record: record["source_order"])
    )
    rows.extend(
        (legacy_asset_url(asset), asset["destination"], "asset", "migrated", asset["optimization"])
        for asset in canonical_asset_records(assets)
    )
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["legacy_url", "new_url", "content_type", "status", "notes"])
        writer.writerows(rows)


def write_review() -> None:
    destination = ROOT / "docs/content-review.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        """# Legacy public content review

This review covers only the supplied public article export, rendered/source public pages, and 61 public assets. No legacy administration, account, credential, deployment, or internationalisation material was migrated.

## Required editorial follow-up

- **Broken recruitment PDF:** legacy article 3 links to `Advertising-template-for-Post-Doctoral-Research-Fellow_Computing.pdf`, but that file is absent from the supplied public assets. The original URL is retained as a legacy referenced URL and no placeholder PDF was created.
- **Missing light logo:** rendered news content references `img/logo/logo-light.png`, but `logo-light.png` is absent from the supplied assets. No substitute was invented.
- **Cloudflare email path:** the rendered group page replaces public email addresses with `/cdn-cgi/l/email-protection`. Profiles were imported from the supplied public source page so the Cloudflare path and scripts were not migrated.
- **Duplicate person provenance:** the supplied legacy source contains separate current and alumni Jiaqi Ge records. Both remain preserved in the immutable provenance manifest; the live editorial roster may retain, merge, or remove entries as membership changes.
- **Duplicate publication:** the two SolGuard citations are preserved as distinct source rows (`publication-060` and `publication-065`) and share the `solguard-external-call-issues` duplicate group.
- **Ten-versus-nine heading:** the legacy heading says “Ten Career-Best Research Outputs”, but only nine records occur before “Book Chapters”. The heading and all nine records are preserved without fabricating a tenth.
- **DNS-broken Auckland profile:** Dr Xuyun Zhang's legacy homepage points to `https://unidirectory.auckland.ac.nz/profile/xuyun-zhang/`. It is retained and flagged for manual replacement because the legacy host does not resolve reliably.
- **Bot-blocked external links:** some third-party profile and media endpoints reject automated requests or return challenge pages. They are retained rather than being marked broken solely from bot responses and require manual browser review.

## Asset handling

All 61 supplied public assets were copied into the new public asset structure. The three valid supplied PDFs are under `assets/documents`. JPEGs larger than 1 MB are orientation-corrected, resized to at most 2000 pixels on the longest edge, and re-encoded with the pinned Pillow version and fixed JPEG settings. Source and destination SHA-256 hashes and per-file handling are recorded in `content-manifest.yml`.

## People provenance and live roster

The 37 supplied legacy profiles, source labels, and duplicate accounting remain preserved in `content-manifest.yml` for provenance. The live `_people` collection is editorially maintained, is not rewritten by the importer, and may add, update, regroup, or remove members without changing the immutable source snapshot. Person Markdown bodies contain biography prose only; role, affiliation, email, phone, and homepage remain structured front matter fields.

## Reproduce

From the repository root, create an isolated environment and install the pinned migration dependency:

```sh
python3 -m venv /tmp/itseg-migrate-venv
/tmp/itseg-migrate-venv/bin/python -m pip install -r requirements-legacy-migration.txt
/tmp/itseg-migrate-venv/bin/python scripts/import_legacy_content.py
/tmp/itseg-migrate-venv/bin/python scripts/validate_site.py --check-source-fidelity
```

The final command is the authoritative full source-fidelity check. A normal `python3 scripts/validate_site.py` remains usable in CI without the `/tmp` source snapshot and prints the full command needed for source-fidelity verification. The importer reads only the safe public inputs listed in `content-manifest.yml`. Collection and migrated-asset output directories are managed roots: the importer refuses symlinked or out-of-repository roots and never follows output symlinks. On reruns it replaces the immutable `legacy-import` news, project, publication, and asset baselines while preserving editorial records. It parses the 37 legacy people records only to refresh provenance metadata and never rewrites the live editorial `_people` collection.

## Global site completion

The ITSEG collection indexes, layouts, includes, Jekyll configuration, navigation, contact page, sitemap, robots policy, and other global pages were completed after the source-fidelity migration. The URL map now marks the five global legacy destinations as migrated. These global presentation files remain outside the authoritative legacy title/body comparison; collection records, structured publication data, review flags, and manifest-managed assets remain governed by the checks above.
""",
        encoding="utf-8",
    )


def write_manifest(news, people, projects, publications, assets) -> None:
    publication_counts = Counter(record["category"] for record in publications)
    people_counts = Counter(record["category"] for record in people)
    project_counts = Counter(record["category"] for record in projects)
    provenance_paths = [
        ARTICLES,
        RENDERED_SOURCE_FILES["news"],
        RENDERED_SOURCE_FILES["people"],
        PUBLIC_SOURCE_FILES["publications"],
        PUBLIC_SOURCE_FILES["people"],
        PUBLIC_SOURCE_FILES["projects"],
    ]
    manifest = {
        "schema_version": 1,
        "scope": "legacy-public-content-and-assets-only",
        "source_inputs": [
            "/tmp/itseg_public_articles.json",
            "/tmp/itseg-legacy-public/html/news.html",
            "/tmp/itseg-legacy-public/html/group.html",
            "/tmp/itseg-legacy-public/html/publications.html",
            "/tmp/itseg-legacy-public/source/group.php",
            "/tmp/itseg-legacy-public/source/projects.php",
            "/tmp/itseg-legacy-public/assets/{group,projects,logo,background,doc}",
        ],
        "source_provenance": [
            {"path": str(path), "sha256": sha256(path)}
            for path in provenance_paths
        ],
        "counts": {
            "news": len(news),
            "people": len(people),
            "people_source_records": sum(record["source_records"] for record in people),
            "projects": len(projects),
            "publications": len(publications),
            "assets": len(assets),
            "pdfs": sum(asset["source_category"] == "doc" for asset in assets),
        },
        "source_title_body_counts": {
            "news": {"titles": len(news), "bodies": len(news)},
            "people": {"titles": len(people), "bodies": len(people)},
            "projects": {"titles": len(projects), "bodies": len(projects)},
            "publications": {"titles": len(publications), "bodies": len(publications)},
        },
        "people_sections": dict(people_counts),
        "people_section_labels": SECTIONS,
        "project_categories": dict(project_counts),
        "publication_categories": dict(publication_counts),
        "collections": {
            "news": canonical_collection_records("news", news),
            "people": canonical_collection_records("people", people),
            "projects": canonical_collection_records("projects", projects),
        },
        "assets": canonical_asset_records(assets),
        "flags": [
            {"id": "broken-recruitment-pdf", "status": "flagged", "legacy_article_id": "3"},
            {"id": "missing-logo-light", "status": "flagged", "legacy_path": "/img/logo/logo-light.png"},
            {"id": "cloudflare-email-path", "status": "excluded", "legacy_path": "/cdn-cgi/l/email-protection"},
            {"id": "duplicate-person-jiaqi-ge", "status": "preserved", "records": ["jiaqi-ge-current.md", "jiaqi-ge-alumni.md"]},
            {"id": "duplicate-publication-solguard", "status": "preserved", "records": ["publication-060", "publication-065"]},
            {"id": "ten-versus-nine-heading", "status": "flagged", "record_count": 9},
            {"id": "dns-broken-auckland-profile", "status": "flagged", "url": "https://unidirectory.auckland.ac.nz/profile/xuyun-zhang/"},
            {"id": "bot-blocked-external-links", "status": "manual-review-required"},
        ],
    }
    destination = ROOT / "docs/content-manifest.yml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    errors = managed_root_errors()
    if errors:
        raise SystemExit("Refusing to operate on unsafe managed output roots: " + "; ".join(errors))
    require_inputs()
    prepare_managed_roots()
    previous = manifested_legacy_paths(load_previous_manifest())
    news = import_news()
    people = import_people(write_output=False)
    projects = import_projects()
    publications = import_publications()
    assets = copy_assets()
    current = {record["file"] for record in [*news, *people, *projects]}
    current.update(record["destination"].lstrip("/") for record in assets)
    remove_stale_legacy_outputs(previous, current)
    write_url_map(news, assets)
    write_review()
    write_manifest(news, people, projects, publications, assets)
    print(
        "Imported 14 news, retained 37 people provenance records, imported 8 projects, "
        "116 publications, and 61 public assets; the live people roster was preserved."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
