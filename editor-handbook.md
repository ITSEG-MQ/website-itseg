# ITSEG editor handbook

## Site structure

The navigation has six public destinations: Home, News, People, Projects, Publications, and Contact.

- `index.html`, `news/index.html`, `people/index.html`, `projects/index.html`, `publications/index.html`, and `contact/index.html` are the public index pages.
- `_news`, `_people`, and `_projects` are Jekyll collections. Their stable URLs are set by each record’s `permalink`.
- `_data/publications.yml` contains the publication list.
- `_layouts` defines the common page and collection-item presentation.
- `_includes` contains the header, footer, cards, and review-status message.
- `assets/css/main.css` and `assets/css/extra.scss` contain the visual system.

## Editing principles

The migrated collections, publication data, and manifest-managed images are source-fidelity records. Do not silently remove, merge, rename, or rewrite them. In particular:

- retain both Jiaqi Ge records and their review flags;
- retain the three profiles marked `legacy-commented-public-source`;
- retain both duplicate SolGuard publication rows;
- retain the “Ten Career-Best Research Outputs” heading with its nine source records;
- do not link or invent a replacement for the missing recruitment PDF.

For a new news, person, or project record, copy the field structure of a current record, use a unique lowercase filename, add a stable permalink, and use only verified information. Every image displayed by a template needs meaningful context, explicit dimensions, and lazy loading unless it is the primary site logo.

## Links and accessibility

Use `relative_url` for internal links so both staging and beta URLs work. Body links remain underlined. If a link deliberately opens a new tab, include `target="_blank" rel="noopener noreferrer"`. Keep headings in order, provide useful image alternative text, and do not add JavaScript-only navigation or interactions.

## Preview and checks

Build with staging settings:

```sh
jekyll serve --config _config.yml
```

Then run:

```sh
python3 scripts/validate_site.py --site _site
python3 -m unittest discover -s tests -v
```

Ask a maintainer before changing configuration, layouts, workflows, the validator, the migration scripts, or any manifest-managed record.
