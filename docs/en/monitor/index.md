# ADN Monitor (overview)

**ADN Monitor** is a separate project from the **ADN DMR Peer Server**, but the two are normally deployed **together**: the server sends **TCP reports** (config, bridges, call events) to the monitor; the monitor drives the **web dashboard** (React) and **WebSocket** live updates. Optional components include the **PHP API** (Slim), **MySQL** (self-service / device registry), and the **hotspot proxy** (UDP between hotspots and the peer server).

This chapter documents the **adn-monitor** stack at the same level of detail as the server guides. Source code lives in the **adn-monitor** repository, not in the **adn-server** repository (where this documentation is maintained).

## What each part does

| Part | Role |
|------|------|
| **`monitor/monitor.py`** | Python (Twisted): connects to the peer server’s **report TCP** port, decodes netstring payloads (`CONFIG_SND`, `BRIDGE_SND`, `BRDG_EVENT`), maintains **CTABLE** / **BTABLE**, writes **Last Heard** / TG stats to **MySQL** when configured, serves **WebSocket** JSON to the dashboard. |
| **`backend/`** | PHP **Slim** app: `/api/config/dashboard`, auth, optional **self-service** APIs, alias proxies. Reads the **same** `adn-mon.yaml` via **`ADN_CONFIG_PATH`**. |
| **`frontend/`** | React (Vite): dashboard UI; consumes backend API + WebSocket. |
| **`proxy/`** | Python (Twisted): UDP **hotspot proxy**; forwards Homebrew between hotspots and the peer server; reads **`Clients`** in MySQL for **RPTO** options (self-service). |

## Single configuration file

**`adn-mon.yaml`** (path often set with **`ADN_CONFIG_PATH`** in `.env`) is shared by:

- Python monitor (`monitor.py`)
- PHP backend (`backend/public/index.php`)
- Hotspot proxy (`proxy/proxy.py`)

So **one** YAML drives reporting addresses, dashboard strings, WebSocket port, **SELF_SERVICE** DB credentials, and **PROXY** listen/range settings.

## Link to the peer server

| Server (`adn-server.yaml`) | Monitor (`adn-mon.yaml`) |
|----------------------------|---------------------------|
| **`REPORTS.REPORT_CLIENTS`** — list of IPs allowed to connect **to** the report listener, or the monitor host | **`ADN_CONNECTION.ADN_IP`** / **`ADN_PORT`** — where the **monitor connects** (must match the server’s report bind and port). |
| **`REPORTS.REPORT_PORT`** — TCP port the **server listens on** for incoming report connections | Same port as **`ADN_PORT`**. |

See [Monitoring and reports](../server/user-guide/monitoring.md) for report opcodes and [Monitor configuration](configuration.md) for every `adn-mon.yaml` section.

## See also

- [Hotspot proxy](hotspot-proxy.md) — `PROXY`, peer server port range, how the process loads config and runs
- [Architecture and deployment](architecture.md)
- [Configuration (`adn-mon.yaml`)](configuration.md)
- [Self-service](self-service.md)
