# ITSEG maintainer handbook

## Environments

- Staging: `_config.yml`, `https://itseg-mq.github.io/website-itseg`
- Beta production: `_config_prod.yml`, `https://beta.itseg.org` with an empty base URL

Both files are complete configurations. They define identical collections, layouts, metadata, exclusions, and verified contact details; only environment URL settings differ.

## Local build

Do not mutate the global macOS Ruby. Use an existing suitable Jekyll installation or an isolated Ruby environment. Build staging with:

```sh
jekyll build --config _config.yml
python3 scripts/validate_site.py --site _site
```

Build beta production with:

```sh
jekyll build --config _config_prod.yml
python3 scripts/validate_site.py --site _site
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

The validator enforces the exact migration counts (14 news, 37 people source records, 8 projects, 116 publications), source-review flags, managed asset hashes, global page metadata, landmarks, images, Liquid rendering, and internal links. Do not weaken the migration assertions to make a content change pass.

## CI and beta release

The validation workflow runs on feature branches, pull requests, and manual dispatch. It performs source validation, builds the staging site, validates generated HTML, and never publishes a release.

The release workflow retains its existing automatic `main` and manual triggers and its rolling `prod` release tag. It validates source before building with `_config_prod.yml`, validates generated HTML before packaging, and only then replaces `site.zip` on the existing release. The packaged site is intended for the beta host at `https://beta.itseg.org`.

Do not commit deployment archives, generated `_site` output, source snapshots, credentials, API keys, private keys, `.env` files, or platform secrets. Configure deployment secrets only in the hosting platform’s protected secret store.

## Migration ownership

`scripts/import_legacy_content.py` owns the three collections and manifest-managed assets. `docs/content-manifest.yml`, `docs/content-review.md`, and `docs/legacy-url-map.csv` document provenance and review status. Preserve `LICENSE` and its template attribution in the footer and README.
