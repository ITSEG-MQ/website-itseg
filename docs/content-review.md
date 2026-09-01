# Legacy public content review

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
