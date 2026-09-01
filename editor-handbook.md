# ITSEG editor handbook

## Site structure

The navigation has six public destinations: Home, News, People, Projects, Publications, and Contact.

- `index.html`, `news/index.html`, `people/index.html`, `projects/index.html`, `publications/index.html`, and `contact/index.html` are the public index pages.
- `_news`, `_people`, and `_projects` are Jekyll collections. Their stable URLs are set by each record’s `permalink`.
- `_data/publications.yml` contains the publication list.
- `_layouts` defines the common page and collection-item presentation.
- `_includes` contains the header, footer, content cards, and publication-list component.
- `assets/css/main.css` and `assets/css/extra.scss` contain the visual system.

## Editing principles

Every content record has an ownership marker. Migration-managed news, project, and publication records use `managed_by: "legacy-import"`; new records use `managed_by: "editorial"`. The live `_people` collection is fully editorial, has no fixed member count, and is not rewritten by the legacy importer. Never mark a new record `legacy-import`, edit `docs/content-manifest.yml` to register it, or place a new image in an importer-managed directory.

The migration manifest remains an immutable provenance baseline. It preserves the original 37 people source records and source-review flags without constraining the live roster. Do not silently rewrite migration-managed news, project, publication, or asset data. In particular:

- retain both duplicate SolGuard publication rows;
- retain the “Ten Career-Best Research Outputs” heading with its nine source records;
- do not link or invent a replacement for the missing recruitment PDF.

Use a unique lowercase, hyphenated ID such as `2026-example-award`; the collection filename must be `<id>.md` and its permalink must be `/<collection>/<id>/`. IDs and permalinks must not duplicate another record. Use only verified information. Images for new records must be raster files (`.jpg`, `.jpeg`, `.png`, `.webp`, or `.gif`) in the matching upload directory:

- news: `assets/uploads/news/`
- people: `assets/uploads/people/`
- projects: `assets/uploads/projects/`

Do not put editorial uploads in `assets/pic/people`, `assets/pic/projects`, `assets/pic/brand`, or `assets/documents`; those directories contain the exact manifest-managed legacy asset set.

## Add news

1. Add the cover image under `assets/uploads/news/`.
2. Create `_news/<id>.md` with these fields and a non-empty body:

```yaml
---
managed_by: "editorial"
id: "2026-example-award"
title: "Example award announcement"
date: "2026-09-01"
cover: "/assets/uploads/news/example-award.jpg"
permalink: "/news/2026-example-award/"
---

Write the announcement here.
```

## Add a person

1. Add the portrait under `assets/uploads/people/`. Existing migrated portraits under `assets/pic/people/` may continue to be referenced by their current records.
2. Choose an unused positive integer `order`. Orders must be unique but do not need to be contiguous, so the roster can grow or shrink without renumbering every profile.
3. Create `_people/<id>.md` with these fields and a non-empty biography:

```yaml
---
managed_by: "editorial"
id: "example-researcher"
title: "Dr Example Researcher"
role: "Research Fellow"
category: "program-leaders"
section: "Program Leaders"
image: "/assets/uploads/people/example-researcher.jpg"
affiliation: "Macquarie University"
email: ""
phone: ""
homepage: "https://example.edu/profile"
order: 38
permalink: "/people/example-researcher/"
---

Write biography prose here. Do not repeat role, affiliation, email, phone, or homepage labels in the body.
```

`category` must be one of `director`, `advisory-board`, `industry-supervisor`, `program-leaders`, `current-researchers`, or `alumni-and-visiting-scholars`; `section` must use the matching heading already shown on the People page. `role`, `email`, `phone`, and `homepage` are optional and may be empty; empty roles are omitted from the rendered card and profile. A homepage, when present, must be an absolute `https://` or `http://` URL.

## Add a project

1. Add the image under `assets/uploads/projects/`.
2. Choose an unused integer `order` greater than 8.
3. Create `_projects/<id>.md` with these fields and a non-empty description:

```yaml
---
managed_by: "editorial"
id: "example-trustworthy-systems-project"
title: "Example Trustworthy Systems Project"
category: "grants"
section: "Australia National Competitive Grants"
image: "/assets/uploads/projects/example-project.jpg"
order: 9
permalink: "/projects/example-trustworthy-systems-project/"
---

Write the project description here.
```

Use category `grants` or `other`, because those are the categories rendered by the Projects page.

## Add a publication

Append one JSON-compatible YAML object to the list in `_data/publications.yml`:

```json
{
  "managed_by": "editorial",
  "id": "publication-2026-example-title",
  "title": "Example publication title",
  "authors": "A. Author and B. Author",
  "publisher": "Example Journal, 2026",
  "category": "Refereed Journal Articles"
}
```

The ID must be a unique lowercase, hyphenated value and must not reuse any baseline publication ID (`publication-001` through `publication-116`). Until page support is extended, `category` must be exactly one of `Ten Career-Best Research Outputs`, `Book Chapters`, `Fully Referred Conference Proceedings`, or `Refereed Journal Articles`. Keep the surrounding JSON commas valid.

## Links and accessibility

Use `relative_url` for internal links so both staging and beta URLs work. Body links remain underlined. If a link deliberately opens a new tab, include `target="_blank" rel="noopener noreferrer"`. Keep headings in order, provide useful image alternative text, and do not add JavaScript-only navigation or interactions.

## Preview and checks

Build with staging settings:

```sh
jekyll serve --config _config.yml
```

Then run:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/validate_site.py --site _site --config _config.yml
git diff --check
```

The legacy importer can be rerun safely: it regenerates the exact manifest baseline for news, projects, publications, assets, and the 37-record people provenance snapshot. It preserves the live editorial `_people` collection and other collection files or publication rows marked `managed_by: "editorial"`. Validation rejects a new or unlisted migration-managed news, project, publication, or asset record.

Ask a maintainer before changing configuration, layouts, workflows, the validator, the migration scripts, or any manifest-managed record.
