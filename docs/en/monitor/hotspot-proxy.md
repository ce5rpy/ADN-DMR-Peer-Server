# Hotspot proxy

The **hotspot proxy** is part of the **adn-monitor** repository. It is a **UDP relay** between **DMR hotspots** (Homebrew / HBP) and the **ADN DMR Peer Server** MASTER: each connected hotspot is mapped to a **dedicated destination port** on the peer server host so many hotspots can share one public IP without port clashes.

Source layout: `proxy/proxy.py`, package `proxy/src/adn_proxy/` (clean architecture). **GPL v3** (derivative of Simon Adlem, G7RZU’s original proxy).

### Why it ships with the monitor (not inside the peer server)

There is no single mandatory layout for every deployment, but **today the proxy lives in the adn-monitor repo** on purpose:

- **Same deployment** as the dashboard stack: **`ADN_CONFIG_PATH`** / **`ADN_PROXY_CONFIG_PATH`**, **`adn-monitor.yaml`** + **`adn-proxy.yaml`**, and usually the same host as **PHP** and **MySQL**.
- **Self-service** ( **`Clients`**, RPTO, **`modified`**) is built around that ecosystem; the peer server binary does not own that database or the **`PROXY`** block.
- **Role split:** the **ADN DMR Peer Server** is the **radio core** (HBP/OpenBridge, bridges, voice, TCP reports). The hotspot proxy is an **optional UDP front** toward a MASTER that already listens on a port **range** — useful when many hotspots share one public address.

**Bundling the proxy into the peer server** (one binary, one `adn-server.yaml`) is conceivable for packaging, but it implies **merging configuration**, **rethinking self-service wiring**, and extra maintenance — only worth it if you explicitly want a single deployable “all-in-one” server.

---

## Configuration file {#configuration-file}

The proxy does **not** use `adn-server.yaml`. It reads YAML that contains **`PROXY`**, **`SELF_SERVICE`**, and **`LOGGER`** (proxy log).

### Resolution order

| Priority | Source | Purpose |
|----------|--------|---------|
| 1 | **`python proxy/proxy.py --config /path/to/file.yaml`** | Overrides config path for this process only. |
| 2 | **`ADN_PROXY_CONFIG_PATH`** | Optional env: absolute path to **`adn-proxy.yaml`** (typical dedicated proxy config). |
| 3 | **`ADN_CONFIG_PATH`** | Legacy: absolute path to a **combined** file (e.g. **`adn-monitor.yaml`** with **PROXY** embedded — same as monitor/backend). |
| 4 | **Default** | **`proxy/adn-proxy.yaml`** next to `proxy/proxy.py` when neither env var is set. |

Copy **`proxy/adn-proxy.example.yaml`** to **`proxy/adn-proxy.yaml`** and edit. **`SELF_SERVICE`** must match **`monitor/adn-monitor.yaml`** (same DB credentials and PBKDF2 parameters).

Sections read from whichever file is chosen:

- **`PROXY`** — listen address, master host, destination port **range**, timeouts, debug, block lists.
- **`SELF_SERVICE`** — MySQL and **`USE_SELFSERVICE`** (for **`Clients`** table, RPTO / options).
- **`LOGGER`** — **`LOG_PATH`** and **`PROXY_LOG_FILE`** (separate from **`LOG_FILE`** in `adn-monitor.yaml` for `monitor.py`).

Optional **environment** overrides (see `proxy/README.md` in the repo): e.g. **`ADN_PROXY_DEBUG`**, **`ADN_PROXY_LISTENPORT`**.

---

## `PROXY` keys (in `adn-proxy.yaml`, or legacy combined YAML)

| Key | Role |
|-----|------|
| **MASTER** | IP or **hostname** of the **ADN DMR Peer Server** host. Resolved to an IPv4 address at startup (Twisted requires an IP for `write()`). |
| **LISTEN_PORT** | UDP port where **hotspots** connect **to the proxy** (the address users configure on the hotspot). |
| **LISTEN_IP** | Empty often means all interfaces; otherwise bind to this address. |
| **PORT** / **DESTPORT_START** | Base UDP port on **`MASTER`** (alias **DESTPORT_START**); must match **`SYSTEM.PORT`** in `adn-server`. |
| **GENERATOR** | Same integer as **`SYSTEM.GENERATOR`**; UDP ports **`PORT`…`PORT+GENERATOR-1`** on **`MASTER`** (one per proxied hotspot session). |
| **TIMEOUT** | Idle / session timeout (seconds). |
| **STATS** | Extra statistics logging. |
| **DEBUG** | Verbose packet logging (or use **`ADN_PROXY_DEBUG=1`**). |
| **CLIENT_INFO** | Per-client info in logs. |
| **BLACK_LIST** / **IP_BLACK_LIST** | Block radio IDs or source IPs. |

Internal config keys (after load) use mixed-case names (`Master`, `ListenPort`, …) — see `adn_proxy.infrastructure.config_loader`.

---

## Peer server (`adn-server.yaml`) must cover the port range

The proxy forwards traffic to **`MASTER:assigned_port`** for each client, where **assigned_port** is picked from **`PORT`…`PORT+GENERATOR-1`** (same **PORT**/**GENERATOR** semantics as [Server configuration](../server/user-guide/configuration.md)).

The **ADN DMR Peer Server** must **listen on UDP** on **that host** for **every port** in that range (usually via **`GENERATOR`** on one SYSTEM block).

- Align **`PROXY.PORT`** and **`PROXY.GENERATOR`** with **`SYSTEM.PORT`** and **`SYSTEM.GENERATOR`** in **`adn-server.yaml`**.
- Typical setup: one **`MODE: MASTER`** entry with **`GENERATOR`** expanding to `SYSTEM-0`…`SYSTEM-(N-1)` on consecutive UDP ports — see [Server configuration](../server/user-guide/configuration.md).

If the server only listens on e.g. **56400** but the proxy sends to **56401**, that client will not register.

---

## How the process starts

1. Resolve config path (`--config`, **`ADN_PROXY_CONFIG_PATH`**, **`ADN_CONFIG_PATH`**, or default **`proxy/adn-proxy.yaml`**).
2. **`load_config()`** parses YAML → **`PROXY`**, **`SELF_SERVICE`**, **`LOG`**.
3. Optional **MySQL** pool if self-service / DB features are enabled.
4. Twisted **reactor** runs UDP **ProxyProtocol** on **`LISTEN_IP:LISTEN_PORT`**, forwarding to **`MASTER:assigned_dest_port`**.

Run (from adn-monitor root):

```bash
# Dedicated proxy YAML (recommended)
export ADN_PROXY_CONFIG_PATH=/opt/adn-monitor/proxy/adn-proxy.yaml
python proxy/proxy.py

# Or rely on default proxy/adn-proxy.yaml after copying from adn-proxy.example.yaml
python proxy/proxy.py

# Legacy: single combined monitor YAML
export ADN_CONFIG_PATH=/opt/adn-monitor/monitor/adn-monitor.yaml
python proxy/proxy.py

# Or explicit path for one run
python proxy/proxy.py --config /opt/adn-monitor/proxy/adn-proxy.yaml
```

Use **systemd** or another supervisor to run alongside **`monitor.py`** and the **PHP** stack.

---

## RPTO, options, and self-service

The proxy **never** sends **RPTO** directly to the hotspot for self-service updates. It sends **RPTO to the MASTER** (peer server); the server updates bridge/options and the normal HBP path applies.

| Event | Proxy behaviour |
|-------|------------------|
| ~**10 s** after hotspot login (**RPTC**) | Read **`Clients.options`** from DB → **RPTO** → master `(MASTER, dport)`. |
| Every ~**10 s** | Rows with **`modified = 1`** → **RPTO** → master, then clear **`modified`**. |
| Hotspot sends **RPTO** | Forward to master; DB updates as implemented. |

Details: [Self-service](self-service.md) and the **adn-monitor** `proxy/README.md`.

---

## Monitor visibility

Hotspots appear on the dashboard only if the **peer server** sends **TCP reports** to the same host/port as **`ADN_CONNECTION`** in **`adn-monitor.yaml`**. Align **`REPORTS`** on the server with **`ADN_IP` / `ADN_PORT`**. See [Monitoring and reports](../server/user-guide/monitoring.md).

---

## See also

- [Monitor configuration](configuration.md) — **`adn-monitor.yaml`** (dashboard, reports, MySQL for backend/monitor); **`PROXY`** detail above.
- [Architecture](architecture.md) — where the proxy sits in the stack.
- [Self-service](self-service.md) — DB, **`modified`**, RPTO timing.
