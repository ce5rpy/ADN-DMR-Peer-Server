# Configuración (`adn-monitor.yaml`)

Este documento describe **`adn-monitor.yaml`**, usado por el **monitor Python** (`monitor/monitor.py`) y el **backend PHP** (`backend/public/index.php`). La ruta por defecto suele ser **`monitor/adn-monitor.yaml`** (sobrescribible con **`ADN_CONFIG_PATH`**).

**Proxy hotspot integrado:** **`PROXY`** y **`SELF_SERVICE`** en **`adn-server.yaml`** (ver [Proxy hotspot (integrado)](../server/user-guide/hotspot-proxy.md)). **Independiente (legado):** **`proxy/adn-proxy.yaml`** — ver [Proxy hotspot](hotspot-proxy.md). **`SELF_SERVICE`** (MySQL / PBKDF2) debe ser **idéntica** entre **`adn-server.yaml`**, **`adn-monitor.yaml`** y **`adn-proxy.yaml`** legado si se usa.

El ejemplo del repositorio **adn-monitor** (`monitor/adn-monitor.yaml.example`) es la plantilla del monitor; las claves siguientes coinciden con ese fichero y `monitor/src/adn_monitor/infrastructure/config_loader.py` (los nombres internos pueden diferir).

---

## `GLOBAL`

| Clave | Significado |
|-------|-------------|
| **BRIDGES_INC** | Mostrar estado de bridges en el panel si es `true`. |
| **HOMEBREW_INC** | Incluir estado HBP peer/master. |
| **LASTHEARD_INC** | Activar funciones / tablas Last Heard. |
| **LASTHEARD_ROWS** | Filas para widgets Last Heard. |
| **EMPTY_MASTERS** | Mostrar masters sin peers. |
| **TGCOUNT_INC** | Activar página / estadísticas de conteo de TG. |
| **TGCOUNT_ROWS** | Filas para el conteo de TG. |
| **TIMEZONE** | Zona horaria IANA (p. ej. `America/Santiago`) para mostrar; vacío usa la hora local del servidor. |

---

## `ADN_CONNECTION` {#adn_connection}

Debe coincidir con la configuración de informes del **ADN DMR Peer Server**.

| Clave | Significado |
|-------|-------------|
| **ADN_IP** | Host/IP donde está el **listener TCP de informes** del peer server (vista de red desde el monitor). |
| **ADN_PORT** | Puerto TCP — debe ser igual a **`REPORTS.REPORT_PORT`** en el servidor y ser alcanzable. |
| **HELLO_TIMEOUT_MS** | Tras conectar por TCP, tiempo de espera del opcode **`0xFF` HELLO** (JSON) desde **ADN DMR Server**. Si no llega a tiempo, el monitor trata el peer como **legado** (solo CONFIG/BRIDGE pickle). Por defecto **1500** ms. Ver [Monitor e informes](../server/user-guide/monitoring.md). |

---

## `SELF_SERVICE`

Credenciales MySQL y parámetros PBKDF2 para **login** y acceso a la tabla **`Clients`**. **PBKDF2_SALT** y **PBKDF2_ITERATIONS** deben coincidir con **`hotspot_proxy_self_service.py`** (o tu herramienta de registro de contraseñas) para que los hashes verifiquen en PHP y Python.

| Clave | Significado |
|-------|-------------|
| **USE_SELFSERVICE** | Lo usa el cargador de config del **proxy** para rutas con BD / self-service (ver README del proxy). |
| **DB_SERVER**, **DB_USERNAME**, **DB_PASSWORD**, **DB_NAME**, **DB_PORT** | Conexión MySQL para **`Clients`** (y tablas relacionadas). |

Si el backend PHP no puede conectar, las rutas de **auth** y **self-service** no se registran (ver `backend/public/index.php`).

---

## `PROXY`

**Proxy UDP hotspot** — guía completa: [Proxy hotspot](hotspot-proxy.md). Los despliegues **integrados** usan **`PROXY`** en **`adn-server.yaml`** (fan-in, sin rango de puertos). Los layouts **independientes** mantienen estas claves en **`proxy/adn-proxy.yaml`** (o fichero combinado legado vía **`ADN_CONFIG_PATH`**).

**Resumen independiente:** **`PORT`** + **`GENERATOR`** deben coincidir con **`SYSTEM.PORT`** + **`SYSTEM.GENERATOR`** en `adn-server`; cada cliente se reenvía a **`MASTER`** en un puerto UDP dentro de **`PORT`…`PORT+GENERATOR-1`** (ver también [Arquitectura](architecture.md)).

| Clave | Significado |
|-------|-------------|
| **MASTER** | Host del peer server (IP o DNS; resuelto al arrancar el proxy). |
| **LISTEN_PORT** / **LISTEN_IP** | Dónde el proxy acepta UDP del hotspot (IP vacía suele significar todas las interfaces). |
| **PORT** / **DESTPORT_START** | Puerto UDP base en **`MASTER`** (el mismo que **PORT** del SYSTEM en el servidor). |
| **GENERATOR** | Cantidad de puertos UDP consecutivos en **`MASTER`** (el mismo entero que **GENERATOR** del SYSTEM en el servidor). |
| **TIMEOUT**, **STATS**, **DEBUG**, **CLIENT_INFO** | Comportamiento y registro. |
| **BLACK_LIST** / **IP_BLACK_LIST** | Listas de bloqueo opcionales. |

---

## `OPB_FILTER`

**Network IDs** separados por comas (como cadenas). El tráfico desde esas fuentes OpenBridge puede **ocultarse** de ciertas rutas de persistencia del panel (ver manejo de `OPB_FILTER` en el controlador del monitor).

---

## `ALIASES`

Misma idea que en el peer server: descargar JSON de **peer / subscriber / TGID** y checksums opcionales. Claves: **PATH**, **\*_FILE**, **\*_URL**, **STALE_HOURS**, **REVIEW_INTERVAL_MINUTES**, **CHECKSUM_***, **TG_LIST_URL**, **BRIDGE_LIST_URL** (proxy del backend para páginas del frontend).

---

## `LOGGER`

| Clave | Significado |
|-------|-------------|
| **LOG_PATH** | Directorio de ficheros de log. |
| **LOG_FILE** | Nombre del log del monitor (p. ej. `adn-monitor.log`). |
| **LOG_LEVEL** | p. ej. `INFO`, `DEBUG`. |

El nombre del fichero de log del **proxy hotspot** se define en **`proxy/adn-proxy.yaml`** dentro de **LOGGER** como **`PROXY_LOG_FILE`** (ver [Proxy hotspot](hotspot-proxy.md)).

---

## `WEBSOCKET_SERVER`

| Clave | Significado |
|-------|-------------|
| **WEBSOCKET_PORT** | Puerto del WebSocket Twisted que envía estado JSON a los navegadores. |
| **FREQUENCY** | Intervalo de envío (segundos). |
| **CLIENT_TIMEOUT** | Cerrar clientes WS inactivos tras N segundos (`0` = desactivado). |
| **USE_SSL**, **SSL_PATH**, **SSL_CERTIFICATE**, **SSL_PRIVATEKEY** | WSS opcional. |

---

## `DASHBOARD`

| Clave | Significado |
|-------|-------------|
| **DASHTITLE** | Título de cabecera. |
| **BACKGROUND** | Usar fondo `bk.jpg` si es `true`. |
| **LANGUAGE** | Idioma por defecto de la UI (`en`, `es`, …). |
| **SELF_SERVICE** | Si es `true`, la UI puede mostrar la entrada **Self-service** (el backend debe exponer API + BD). |
| **SHOW_CONSOLE** | Mostrar página consola (mensajes inicio/fin de llamada). |
| **MIN_DURATION** | Duración mínima de llamada (segundos) para la tabla Last Heard del **panel** (la página Last Heard puede seguir mostrando más cortas). |
| **nav_links**, **footer**, **news** | Enlaces estructurados / marquee opcionales. |

---

## Entorno

- **`ADN_CONFIG_PATH`**: ruta absoluta a **`adn-monitor.yaml`** para el **monitor** y el **backend PHP**.
- **`ADN_PROXY_CONFIG_PATH`** (opcional): ruta absoluta a **`adn-proxy.yaml`** para el proxy hotspot. Si no está definida, el proxy usa **`ADN_CONFIG_PATH`** (fichero combinado legado), luego **`proxy/adn-proxy.yaml`** por defecto — detalles en [Proxy hotspot](hotspot-proxy.md#configuration-file).
- El backend puede usar **`API_BASE_PATH`** si la API va bajo un prefijo.

---

## Ver también

- [Inicio de la documentación](../README.md)
- [Arquitectura](architecture.md)
- [Self-service](self-service.md)
- **`REPORTS`** en el peer server: [Monitor e informes](../server/user-guide/monitoring.md), [Configuración del servidor](../server/user-guide/configuration.md) (sección **`REPORTS`**).
