# Configuration (`adn-monitor.yaml`)

This document describes **`adn-monitor.yaml`**, used by the **Python monitor** (`monitor/monitor.py`) and the **PHP backend** (`backend/public/index.php`). Default path is usually **`monitor/adn-monitor.yaml`** (override with **`ADN_CONFIG_PATH`**).

The **hotspot proxy** loads a **separate** file by default — **`proxy/adn-proxy.yaml`** — see [Hotspot proxy](hotspot-proxy.md). **`SELF_SERVICE`** (MySQL / PBKDF2) must stay **identical** between the two YAML files when both are used.

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

MySQL credentials and PBKDF2 parameters for **login** and **`Clients`** table access. **PBKDF2_SALT** and **PBKDF2_ITERATIONS** must match **`hotspot_proxy_self_service.py`** (or your password-registration tool) so stored password hashes verify in PHP and Python.

| Key | Meaning |
|-----|---------|
| **USE_SELFSERVICE** | Used by the **proxy** config loader to enable DB-backed options / self-service paths (see proxy README). |
| **DB_SERVER**, **DB_USERNAME**, **DB_PASSWORD**, **DB_NAME**, **DB_PORT** | MySQL connection for **`Clients`** (and related) tables. |

If the PHP backend cannot connect, **auth** and **self-service** API routes are not registered (see `backend/public/index.php`).

---

## `PROXY`

Hotspot **UDP proxy** — full guide: [Hotspot proxy](hotspot-proxy.md). In current layouts, these keys live in **`proxy/adn-proxy.yaml`**, not in `adn-monitor.yaml`. **Legacy:** a single file can still contain **PROXY** if the proxy is started with **`ADN_CONFIG_PATH`** pointing at that file (see resolution order in [Hotspot proxy](hotspot-proxy.md#configuration-file)).

Summary: **`PORT`** + **`GENERATOR`** must match **`SYSTEM.PORT`** + **`SYSTEM.GENERATOR`** in `adn-server`; each client is forwarded to **`MASTER`** at one UDP port in **`PORT`…`PORT+GENERATOR-1`** (see also [Architecture](architecture.md)).

| Key | Meaning |
|-----|---------|
| **MASTER** | Peer server host (IP or DNS; resolved at proxy startup). |
| **LISTEN_PORT** / **LISTEN_IP** | Where the proxy accepts hotspot UDP (empty IP often means all interfaces). |
| **PORT** / **DESTPORT_START** | Base UDP port on **`MASTER`** (same as server SYSTEM **PORT**). |
| **GENERATOR** | Count of consecutive UDP ports on **`MASTER`** (same integer as server SYSTEM **GENERATOR**). |
| **TIMEOUT**, **STATS**, **DEBUG**, **CLIENT_INFO** | Behaviour and logging. |
| **BLACK_LIST** / **IP_BLACK_LIST** | Optional block lists. |

---

## `OPB_FILTER`

Comma-separated **network IDs** (as strings). Traffic from those OpenBridge sources can be **hidden** from certain dashboard persistence paths (see monitor controller `OPB_FILTER` handling).

---

## `ALIASES`

Similar idea to the peer server: download **peer / subscriber / TGID** JSON and optional checksums. Keys include **PATH**, **\*_FILE**, **\*_URL**, **STALE_HOURS**, **REVIEW_INTERVAL_MINUTES**, **CHECKSUM_***, **TG_LIST_URL**, **BRIDGE_LIST_URL** (backend proxy for frontend pages).

---

## `LOGGER`

| Key | Meaning |
|-----|---------|
| **LOG_PATH** | Directory for log files. |
| **LOG_FILE** | Monitor log filename (e.g. `adn-monitor.log`). |
| **LOG_LEVEL** | e.g. `INFO`, `DEBUG`. |

The **hotspot proxy** log filename is set in **`proxy/adn-proxy.yaml`** under **LOGGER** as **`PROXY_LOG_FILE`** (see [Hotspot proxy](hotspot-proxy.md)).

---

## `WEBSOCKET_SERVER`

| Key | Meaning |
|-----|---------|
| **WEBSOCKET_PORT** | Port for Twisted WebSocket pushing JSON state to browsers. |
| **FREQUENCY** | Push interval (seconds). |
| **CLIENT_TIMEOUT** | Drop idle WS clients after N seconds (`0` = disable). |
| **USE_SSL**, **SSL_PATH**, **SSL_CERTIFICATE**, **SSL_PRIVATEKEY** | Optional WSS. |

---

## `DASHBOARD`

| Key | Meaning |
|-----|---------|
| **DASHTITLE** | Header title. |
| **BACKGROUND** | Use `bk.jpg` background if `true`. |
| **LANGUAGE** | Default UI language (`en`, `es`, …). |
| **SELF_SERVICE** | If `true`, the UI can show the **Self-service** nav entry (backend must expose API + DB). |
| **SHOW_CONSOLE** | Show console page (call start/end messages). |
| **MIN_DURATION** | Minimum call duration (seconds) for **dashboard** Last Heard table (Last Heard page may still show shorter). |
| **nav_links**, **footer**, **news** | Optional structured links / marquee items. |

---

## Environment

- **`ADN_CONFIG_PATH`**: Absolute path to **`adn-monitor.yaml`** for the **monitor** and **PHP backend**.
- **`ADN_PROXY_CONFIG_PATH`** (optional): Absolute path to **`adn-proxy.yaml`** for the hotspot proxy. If unset, the proxy falls back to **`ADN_CONFIG_PATH`** (legacy combined file), then to **`proxy/adn-proxy.yaml`** by default — details in [Hotspot proxy](hotspot-proxy.md#configuration-file).
- Backend may use **`API_BASE_PATH`** if the API is mounted under a prefix.

---

## See also

- [Documentation home](../README.md)
- [Architecture](architecture.md)
- [Self-service](self-service.md)
- Peer server **`REPORTS`**: [Monitoring and reports](../server/user-guide/monitoring.md), [Server configuration](../server/user-guide/configuration.md) (section **`REPORTS`**).
