# Origen de la documentación

El Markdown publicado con **MkDocs** está en **`en/`** (inglés) y **`es/`** (español). La **entrada por idioma** para GitHub y el sitio generado es **`docs/en/README.md`** o **`docs/es/README.md`**.

| Idioma | `docs_dir` | Salida típica | Comando |
|--------|------------|---------------|---------|
| Inglés | `docs/en` | `site/en/` | `mkdocs build` (usa `mkdocs.yml`) |
| Español | `docs/es` | `site/es/` | `mkdocs build -f mkdocs.es.yml` |

- **Estructura:** `en/server/` y `es/server/` — peer server; `en/monitor/` y `es/monitor/` — ADN Monitor. Las rutas relativas bajo cada locale deben coincidir para facilitar traducciones. Más detalle en [Traducciones](en/server/contributing/translations.md) (EN) / [Traducciones](es/server/contributing/translations.md) (ES).
