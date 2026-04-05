# Translations

## Current layout

**MkDocs** pages exist in parallel trees:

| Locale | Path | Build |
|--------|------|-------|
| English | **`docs/en/`** | `mkdocs.yml` → **`site/en/`** |
| Spanish | **`docs/es/`** | **`mkdocs.es.yml`** → **`site/es/`** |

- **`docs/en/server/`** — ADN DMR Peer Server (user guide, protocols, development, contributing).
- **`docs/en/monitor/`** — ADN Monitor (dashboard, `adn-mon.yaml`, self-service).

Spanish mirrors the same relative paths under **`docs/es/`**.

`mkdocs.yml` sets **`docs_dir: docs/en`** and **`theme.language: en`**. **`mkdocs.es.yml`** sets **`docs_dir: docs/es`** and **`theme.language: es`**.

Build **both** (`mkdocs build` and `mkdocs build -f mkdocs.es.yml`). The outputs land in **`site/en/`** and **`site/es/`**. Publish the combined **`site/`** directory as your HTTP server layout requires.

For a quick local check: `cd site && python -m http.server` then open **`/en/`** and **`/es/`**. Optional: use **`mkdocs-static-i18n`** later for a single build with page-level language pairs.

## Adding or updating a locale

1. Keep **navigation structure** aligned across locales (same relative paths: `server/user-guide/introduction.md`, etc.).
2. Headings that are cross-linked use **`attr_list`** explicit anchors `{#id}` where slugs must stay stable — see Spanish pages for examples.
3. When adding a third locale, add another MkDocs config and output directory following the same pattern.

## Writing for translators

- Use **short, clear sentences**.
- Avoid idioms and culture-specific jokes.
- Keep **terminology** consistent (OpenBridge, BCSQ, TG, `BRIDGES`).
- Put **code identifiers** and **YAML keys** in backticks.

## Not translated by default

- The **repository root** `README.md` may stay English-only or link to the published docs site.
