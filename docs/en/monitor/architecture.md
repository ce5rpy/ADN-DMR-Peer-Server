# Architecture and deployment

## Clean architecture (Python monitor)

Under `monitor/src/adn_monitor/`:

- **Domain** — value objects, errors, opcode types.
- **Application** — `MonitorState`, `process_message` in `monitor_controller.py`, alias service, Last Heard / TG count use cases, time formatting.
- **Infrastructure** — YAML `load_config`, Twisted **TCP client** (`ReportClientFactory`) to the peer server, **WebSocket** factory for the dashboard, MySQL repositories, pickle/json decoders for `CONFIG_SND` / `BRIDGE_SND`.

The monitor **connects outbound** to **`ADN_CONNECTION.ADN_IP:ADN_PORT`** and receives length-prefixed (netstring-style) messages. It updates in-memory **CTABLE** (masters/peers/OpenBridge) and **BTABLE** (bridges), and persists **BRDG_EVENT** outcomes when MySQL is configured.

## Report protocol (from the peer server)

Same opcodes as documented for the server: **CONFIG_SND**, **BRIDGE_SND**, **BRDG_EVENT**, etc. The monitor decodes and applies them in `process_message` — see [Monitoring and reports](../server/user-guide/monitoring.md).

## WebSocket

`monitor.py` runs a Twisted **WebSocket** on **`WEBSOCKET_SERVER.WEBSOCKET_PORT`**, pushing JSON snapshots at **`FREQUENCY`** so the React app updates without polling for core state.

## PHP backend

- **Slim 4** front controller: `backend/public/index.php`.
- Loads **`adn-monitor.yaml`** via **`ADN_CONFIG_PATH`** (same as monitor).
- **`/api/config/dashboard`** — title, language, feature flags (`selfService`, `showConsole`, …) from **`DASHBOARD`**.
- **`/api/auth/*`** — session cookie auth when **SELF_SERVICE** DB is available.
- **`/api/self-service/*`** — device options (see [Self-service](self-service.md)).
- **`/api/aliases/*`** — optional proxy to TG/bridge list URLs from **ALIASES**.

## Frontend

- **Vite + React** under `frontend/`; build produces static assets served by nginx/Apache or similar.
- Uses **`API_BASE`** (build-time) to reach the PHP API and **WebSocket URL** for live data.

## Hotspot proxy

**Integrated (default):** **`adn-server.py`** runs UDP fan-in from **`PROXY.LISTEN_PORT`** into **`PROXY.TARGET_SYSTEM`**; **`SELF_SERVICE`** in **`adn-server.yaml`** drives **RPTO** from MySQL **`Clients`**. See [Hotspot proxy (integrated)](../server/user-guide/hotspot-proxy.md).

**Standalone (legacy, adn-monitor repo):**

- Entry: `proxy/proxy.py`; package `src/adn_proxy/` (domain / application / infrastructure).
- Reads **`PROXY`** and **`SELF_SERVICE`** from **`adn-proxy.yaml`** by default (or from a combined monitor YAML via **`ADN_CONFIG_PATH`** — see [Hotspot proxy](hotspot-proxy.md#configuration-file)).
- For each hotspot client, allocates a UDP port in **`PORT`…`PORT+GENERATOR-1`** and forwards to **`MASTER`**.
- When **self-service** updates **`Clients.options`** and sets **`modified=1`**, the proxy sends **RPTO** to the **master** on a timer (~10 s).

**Details:** [Hotspot proxy](hotspot-proxy.md) (integrated vs standalone, config keys, startup).

## Typical deployment topology

```text
[Hotspots] --UDP--> [Proxy :LISTEN_PORT] --UDP--> [Peer server :PORT..PORT+GENERATOR-1]
                           |
                           v
                    MySQL (Clients)

[Peer server :REPORT_PORT] <--- TCP --- [monitor.py : connects as client]

[Browser] --HTTPS--> [PHP API + static frontend]
[Browser] --WS----> [monitor WebSocket :9000]
```

---

## See also

- [Documentation home](../README.md)
- [Configuration](configuration.md)
- [Self-service](self-service.md)
