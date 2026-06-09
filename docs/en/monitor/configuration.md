# Configuration (`adn-monitor.yaml`)

This document describes **`adn-monitor.yaml`**, used by **`monitor/monitor.py`** (FastAPI: REST, WebSocket, report ingest). Default path is usually **`monitor/adn-monitor.yaml`** (override with **`ADN_CONFIG_PATH`**).

**Hotspot proxy** is configured in **`adn-server.yaml`** (`PROXY` + `SELF_SERVICE`) — see [Hotspot proxy (integrated)](../server/user-guide/hotspot-proxy.md). **`SELF_SERVICE`** (MySQL / PBKDF2) must stay **identical** between **`adn-server.yaml`** and **`adn-monitor.yaml`**.

The example shipped in the **adn-monitor** repo (`monitor/adn-monitor.yaml.example`) is the template for the monitor; keys below match that file and `monitor/src/adn_monitor/infrastructure/config_loader.py` (internal names may differ).

---

## `GLOBAL`

| Key | Meaning |
|-----|---------|
| **BRIDGES_INC** | Show bridge status in the dashboard when `true`. |
| **HOMEBREW_INC** | Include Homebrew (HBP) peer/master status. |
| **LASTHEARD_INC** | Enable Last Heard features / tables. |
| **LASTHEARD_ROWS** | Row count for Last Heard widgets. |
| **EMPTY_MASTERS** | Whether to show masters with no peers. |
| **TGCOUNT_INC** | Enable TG count page / stats. |
| **TGCOUNT_ROWS** | Rows for TG count display. |
| **TIMEZONE** | IANA timezone name (e.g. `America/Santiago`) for display; empty uses server local time. |

---

## `ADN_CONNECTION` {#adn_connection}

Must match the **ADN DMR Peer Server** reporting configuration.

| Key | Meaning |
|-----|---------|
| **ADN_IP** | Host/IP where the **peer server’s report TCP listener** is bound (from the monitor’s network view). |
| **ADN_PORT** | TCP port — must equal **`REPORTS.REPORT_PORT`** on the server and be reachable. |
| **HELLO_TIMEOUT_MS** | After TCP connect, how long to wait for opcode **`0xFF` HELLO** (JSON) from **ADN DMR Server**. If nothing arrives in time, the monitor treats the peer as **legacy** (pickled CONFIG/BRIDGE only). Default **1500** ms. See [Monitoring and reports](../server/user-guide/monitoring.md). |

---

## `SELF_SERVICE`

MySQL credentials and PBKDF2 parameters for **login**, **self-service**, and **`Clients`** table access. **PBKDF2_SALT** and **PBKDF2_ITERATIONS** must match **`hotspot_proxy_self_service.py`** (or your password-registration tool) so stored password hashes verify in the monitor API and **adn-server** integrated proxy.

| Key | Meaning |
|-----|---------|
| **DB_SERVER**, **DB_USERNAME**, **DB_PASSWORD**, **DB_NAME**, **DB_PORT** | MySQL connection for **`Clients`** (and related) tables. |

If MySQL is unavailable, **auth** and **self-service** API routes are not registered.

---

## `OPB_FILTER`

Comma-separated **network IDs** (as strings). Traffic from those OpenBridge sources can be **hidden** from certain dashboard persistence paths (see monitor controller `OPB_FILTER` handling).

---

## `ALIASES`

Similar idea to the peer server: download **peer / subscriber / TGID** JSON and optional checksums. Keys include **PATH**, **\*_FILE**, **\*_URL**, **STALE_HOURS**, **REVIEW_INTERVAL_MINUTES**, **CHECKSUM_***, **TG_LIST_URL**, **BRIDGE_LIST_URL** (API proxy for frontend pages).

---

## `LOGGER`

| Key | Meaning |
|-----|---------|
| **LOG_PATH** | Directory for log files. |
| **LOG_FILE** | Monitor log filename (e.g. `adn-monitor.log`). |
| **LOG_LEVEL** | e.g. `INFO`, `DEBUG`. |

---


## `MONITOR_APP`

| Key | Meaning |
|-----|---------|
| **LISTEN_HOST** | Bind address (`""` = all IPv4). |
| **LISTEN_PORT** | HTTP port (e.g. `8080`): `/api/*` and `/ws`. |
| **INGEST** | `tcp` (client to `ADN_CONNECTION`) or `mqtt` (broker topics). |
| **MQTT** | Required when `INGEST: mqtt` (`URL`, `TOPIC_PREFIX`, `QOS`). |
| **FREQUENCY** | Background periodic resync (seconds); live updates are event-driven. |
| **CLIENT_TIMEOUT** | Drop idle WS clients after N seconds (`0` = disable). |
| **CORS_ORIGINS** | Allowed origins for dev (optional). |

In production, Nginx proxies `/api` and `/ws` to **LISTEN_PORT**. No separate WebSocket port is needed.

Obsolete **`WEBSOCKET_SERVER`** YAML (Twisted on a separate port) is ignored; use **`MONITOR_APP`**.

---

## `DASHBOARD`

| Key | Meaning |
|-----|---------|
| **DASHTITLE** | Header title. |
| **BACKGROUND** | Use `bk.jpg` background if `true`. |
| **LANGUAGE** | Default UI language (`en`, `es`, …). |
| **SELF_SERVICE** | If `true`, the UI can show the **Self-service** nav entry (monitor API + MySQL required). |
| **SHOW_CONSOLE** | Show console page (call start/end messages). |
| **MIN_DURATION** | Minimum call duration (seconds) for **dashboard** Last Heard table (Last Heard page may still show shorter). |
| **nav_links**, **footer**, **news** | Optional structured links / marquee items. |

---

## Environment

- **`ADN_CONFIG_PATH`**: Absolute path to **`adn-monitor.yaml`** for **`monitor.py`**.
- Project root **`.env`**: `VITE_API_BASE`, `VITE_DEFAULT_LANGUAGE` (frontend build); auto-loaded by `monitor.py` and `db_bootstrap.py`.

---

## See also

- [Documentation home](../README.md)
- [Architecture](architecture.md)
- [Self-service](self-service.md)
- Peer server **`REPORTS`**: [Monitoring and reports](../server/user-guide/monitoring.md), [Server configuration](../server/user-guide/configuration.md) (section **`REPORTS`**).
