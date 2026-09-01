# ITSEG website

This repository contains the Jekyll website for the Intelligent Systems Engineering Group (ITSEG) at Macquarie University. It retains the simple Liquid/Jekyll architecture and the original GPL-3.0 `LICENSE` attribution while replacing the former conference site.

## Content

- `_news`: 14 verified legacy news records
- `_people`: 37 verified source records in six groups
- `_projects`: five national competitive grants and three other projects
- `_data/publications.yml`: 116 verified publication records
- `docs/content-manifest.yml`: authoritative migration manifest and asset checksums

Do not edit migration-managed records or assets by hand. See `editor-handbook.md` for routine editing and `maintainer-handbook.md` for validation and release procedures.

## Local build

Use an isolated Ruby environment when one is needed; do not install into the system Ruby. With Jekyll already available:

```sh
jekyll build --config _config.yml
python3 scripts/validate_site.py --site _site
```

The staging configuration builds links for `https://itseg-mq.github.io/website-itseg`. To test the beta production configuration:

```sh
jekyll build --config _config_prod.yml
python3 scripts/validate_site.py --site _site
```

## Validation

```sh
python3 scripts/validate_site.py
python3 -m unittest discover -s tests -v
```

The authoritative legacy source-fidelity check uses the approved public source snapshot and pinned dependencies:

```sh
python3 -m venv /tmp/itseg-migrate-venv
/tmp/itseg-migrate-venv/bin/python -m pip install -r requirements-legacy-migration.txt
/tmp/itseg-migrate-venv/bin/python scripts/validate_site.py --check-source-fidelity
```

No credentials, tokens, private source exports, or deployment secrets belong in this repository.
