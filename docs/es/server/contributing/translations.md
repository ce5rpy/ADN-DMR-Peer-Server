# Traducciones

## Diseño actual

Las páginas **MkDocs** existen en árboles paralelos:

| Idioma | Ruta | Build |
|--------|------|-------|
| Inglés | **`docs/en/`** | `mkdocs.yml` → **`site/en/`** |
| Español | **`docs/es/`** | **`mkdocs.es.yml`** → **`site/es/`** |

- **`docs/en/server/`** — ADN DMR Peer Server (guía de usuario, protocolos, desarrollo, contribución).
- **`docs/en/monitor/`** — ADN Monitor (panel, `adn-mon.yaml`, self-service).

El español replica las mismas rutas relativas bajo **`docs/es/`**.

`mkdocs.yml` usa **`docs_dir: docs/en`** e **`theme.language: en`**. **`mkdocs.es.yml`** usa **`docs_dir: docs/es`** e **`theme.language: es`**.

Genera **las dos** salidas (`mkdocs build` y `mkdocs build -f mkdocs.es.yml`). Quedan en **`site/en/`** y **`site/es/`**. Publica la carpeta **`site/`** según el mapeo de tu servidor HTTP.

Prueba local rápida: `cd site && python -m http.server` y abre **`/en/`** y **`/es/`**. Opcional: **`mkdocs-static-i18n`** más adelante para un solo build con pares de idioma por página.

## Añadir o actualizar un idioma

1. Mantén la **estructura de navegación** alineada entre locales (las mismas rutas relativas: `server/user-guide/introduction.md`, etc.).
2. Los encabezados con enlaces cruzados usan anclas explícitas **`attr_list`** `{#id}` cuando los slugs deben permanecer estables — ver páginas en español.
3. Si añades un tercer idioma, añade otro fichero MkDocs y directorio de salida siguiendo el mismo esquema.

## Escritura para traductores

- Frases **cortas y claras**.
- Evitar modismos y humor cultural.
- **Terminología** coherente (OpenBridge, BCSQ, TG, `BRIDGES`).
- **Identificadores de código** y **claves YAML** entre backticks.

## No traducido por defecto

- El **`README.md` de la raíz** del repositorio puede permanecer solo en inglés o enlazar al sitio de documentación publicado.
