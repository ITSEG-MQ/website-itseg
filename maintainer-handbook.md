# ITSEG maintainer handbook

## Environments

- Staging: `_config.yml`, `https://itseg-mq.github.io/website-itseg`
- Beta production: `_config_prod.yml`, `https://beta.itseg.org` with an empty base URL

Both files are complete configurations. They define identical collections, layouts, metadata, exclusions, and verified contact details; only environment URL settings differ.

## Local build

Do not mutate the global macOS Ruby. Use an existing suitable Jekyll installation or an isolated Ruby environment. Build staging with:

```sh
jekyll build --config _config.yml
python3 scripts/validate_site.py --site _site --config _config.yml
```

Build beta production with:

```sh
jekyll build --config _config_prod.yml
python3 scripts/validate_site.py --site _site --config _config_prod.yml
```

## Required validation

Before a pull request or release, run:

```sh
python3 scripts/validate_site.py
python3 -m unittest discover -s tests -v
git diff --check
```

When the approved public source snapshot is available under `/tmp`, also run the authoritative source-fidelity check:

```sh
python3 -m venv /tmp/itseg-migrate-venv
/tmp/itseg-migrate-venv/bin/python -m pip install -r requirements-legacy-migration.txt
/tmp/itseg-migrate-venv/bin/python scripts/validate_site.py --check-source-fidelity
```

The manifest is an immutable legacy baseline. The validator applies exact counts (14 news, 37 people source records, 8 projects, and 116 publications), legacy IDs, source ordering, source-review flags, hashes, collection map, asset set, and URL map only to records marked `managed_by: "legacy-import"`. It validates additional `managed_by: "editorial"` records generically, so approved additions do not change the baseline manifest.

For any editorial addition, follow the complete field examples in `editor-handbook.md`. In summary:

- collection filenames, `id` values, and permalinks use the same unique lowercase hyphenated ID;
- news requires `title`, `date`, `cover`, and a non-empty body;
- people requires `title`, `role`, a currently rendered `category` and matching `section`, `image`, a unique integer `order` greater than 37, and a non-empty biography;
- projects requires `title`, rendered `category` (`grants` or `other`), `section`, `image`, a unique integer `order` greater than 8, and a non-empty description;
- publications require unique `id`, `title`, `authors`, `publisher`, and one of the four currently rendered categories;
- collection uploads go only under `assets/uploads/news`, `assets/uploads/people`, or `assets/uploads/projects` and never under a manifest-managed asset directory.

All editorial records must set `managed_by: "editorial"`. A record falsely marked `legacy-import` is rejected because it is not part of the manifest baseline.

## CI and beta release

The validation workflow runs on feature branches, pull requests, and manual dispatch. It performs source validation, builds the beta production configuration for an exact deployment preview, validates generated HTML, uploads the preview artifact, and never publishes a release.

The release workflow retains its existing automatic `main` and manual triggers and its rolling `prod` release tag. It validates source before building with `_config_prod.yml`, validates generated HTML before packaging, and only then replaces `site.zip` on the existing release. The packaged site is intended for the beta host at `https://beta.itseg.org`.

Do not commit deployment archives, generated `_site` output, source snapshots, credentials, API keys, private keys, `.env` files, or platform secrets. Configure deployment secrets only in the hosting platform’s protected secret store.

## Migration ownership

`scripts/import_legacy_content.py` owns only the manifest-listed legacy records and legacy asset destinations. It regenerates the baseline, merges existing editorial publication rows back into `_data/publications.yml`, and deletes only stale paths listed in the previous manifest. It does not delete valid editorial collection files, and it does not manage `assets/uploads/`.

To verify importer idempotence when the approved `/tmp` snapshot is present, run the pinned importer twice, then source fidelity and the normal suite:

```sh
/tmp/itseg-migrate-venv/bin/python scripts/import_legacy_content.py
/tmp/itseg-migrate-venv/bin/python scripts/import_legacy_content.py
/tmp/itseg-migrate-venv/bin/python scripts/validate_site.py --check-source-fidelity
python3 -m unittest discover -s tests -v
python3 scripts/validate_site.py
git diff --check
```

`docs/content-manifest.yml`, `docs/content-review.md`, and `docs/legacy-url-map.csv` document legacy provenance and review status. Preserve `LICENSE` and its template attribution in the footer and README.
