# ADN Monitor (overview)

**ADN Monitor** is a separate project from the **ADN DMR Peer Server**, but the two are normally deployed **together**: the server sends **TCP reports** (or MQTT) to the monitor; the monitor drives the **web dashboard** (React) and **WebSocket** live updates. A single **`monitor.py`** process (FastAPI) serves **REST** (`/api/*`), **WebSocket** (`/ws`), and **report ingest**. Optional: **MySQL** (self-service / Last Heard) and **integrated hotspot proxy** in **`adn-server.py`**.

This chapter documents the **adn-monitor** stack at the same level of detail as the server guides. Source code lives in the **adn-monitor** repository, not in the **adn-server** repository (where this documentation is maintained).

## What each part does

| Part | Role |
|------|------|
| **`monitor/monitor.py`** | FastAPI: REST (`/api/*`), WebSocket (`/ws`), TCP or MQTT report ingest, **CTABLE** / Last Heard, self-service MySQL. |
| **`frontend/`** | React (Vite): dashboard UI; same-origin `/api` + `/ws`. |

## Configuration files

| File | Used by | Typical env |
|------|---------|-------------|
| **`adn-server.yaml`** | **`adn-server.py`** (integrated **`PROXY`** / **`SELF_SERVICE`**) | `-c` / default path next to binary |
| **`monitor/adn-monitor.yaml`** | **`monitor.py`** | **`ADN_CONFIG_PATH`** |

**`SELF_SERVICE`** (MySQL / PBKDF2) must **match** between **`adn-server.yaml`** and **`adn-monitor.yaml`**. On the server, MariaDB credentials are in **`DATABASE`** (shared pool for self-service and **`peer_dynamic_tgs`**). **`ADN_CONNECTION`**, dashboard, WebSocket, and aliases live in **`adn-monitor.yaml`**; integrated **`PROXY`** lives in **`adn-server.yaml`** — see [Hotspot proxy (integrated)](../server/user-guide/hotspot-proxy.md).

**Recommended pairing:** **adn-server 2.0.0-rc.3** + **adn-monitor 2.0.0-rc.4** (dynamic TG persistence, TG 4000 monitor sync).

## Link to the peer server

| Server (`adn-server.yaml`) | Monitor (`adn-monitor.yaml`) |
|----------------------------|---------------------------|
| **`REPORTS.REPORT_CLIENTS`** — list of IPs allowed to connect **to** the report listener, or the monitor host | **`ADN_CONNECTION.ADN_IP`** / **`ADN_PORT`** — where the **monitor connects** (must match the server’s report bind and port). |
| **`REPORTS.REPORT_PORT`** — TCP port the **server listens on** for incoming report connections | Same port as **`ADN_PORT`**. |

See [Monitoring and reports](../server/user-guide/monitoring.md) for report opcodes and [Monitor configuration](configuration.md) for every `adn-monitor.yaml` section.

## See also

- [Hotspot proxy (integrated)](../server/user-guide/hotspot-proxy.md) — `PROXY` in `adn-server.yaml`
- [Architecture and deployment](architecture.md)
- [Configuration (`adn-monitor.yaml`)](configuration.md)
- [Self-service](self-service.md)
