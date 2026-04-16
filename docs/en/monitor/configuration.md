# Configuration (`adn-mon.yaml`)

All components read the **same** YAML (default path often `monitor/adn-mon.yaml`; override with **`ADN_CONFIG_PATH`**). The example shipped in the **adn-monitor** repo is the authoritative template; keys below match `monitor/adn-mon.yaml` and `monitor/src/adn_monitor/infrastructure/config_loader.py` (internal names may differ).

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

## `ADN_CONNECTION`

Must match the **ADN DMR Peer Server** reporting configuration.

| Key | Meaning |
|-----|---------|
| **ADN_IP** | Host/IP where the **peer server’s report TCP listener** is bound (from the monitor’s network view). |
| **ADN_PORT** | TCP port — must equal **`REPORTS.REPORT_PORT`** on the server and be reachable. |

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

Hotspot **UDP proxy** — full guide: [Hotspot proxy](hotspot-proxy.md). Summary: forwards each client to **`MASTER:DESTPORT_START`…`DEST_PORT_END`**; the peer server must **listen** on that IP and port range (see also [Architecture](architecture.md)).

| Key | Meaning |
|-----|---------|
| **MASTER** | Peer server host (IP or DNS; resolved at proxy startup). |
| **LISTEN_PORT** / **LISTEN_IP** | Where the proxy accepts hotspot UDP (empty IP often means all interfaces). |
| **DESTPORT_START** / **DEST_PORT_END** | One port per proxied client toward **`MASTER`**. |
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
| **LOG_FILE** | Monitor log filename (e.g. `adn-mon.log`). |
| **PROXY_LOG_FILE** | Separate log name for the proxy (when run with proxy logging). |
| **LOG_LEVEL** | e.g. `INFO`, `DEBUG`. |

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

- **`ADN_CONFIG_PATH`**: Absolute path to `adn-mon.yaml` for monitor, backend, and proxy.
- Backend may use **`API_BASE_PATH`** if the API is mounted under a prefix.

---

## See also

- [Documentation home](../README.md)
- [Architecture](architecture.md)
- [Self-service](self-service.md)
- Peer server **`REPORTS`**: [Monitoring and reports](../server/user-guide/monitoring.md), [Server configuration](../server/user-guide/configuration.md) (section **`REPORTS`**).
