# Hotspot proxy

The **hotspot proxy** is part of the **adn-monitor** repository. It is a **UDP relay** between **DMR hotspots** (Homebrew / HBP) and the **ADN DMR Peer Server** MASTER: each connected hotspot is mapped to a **dedicated destination port** on the peer server host so many hotspots can share one public IP without port clashes.

Source layout: `proxy/proxy.py`, package `proxy/src/adn_proxy/` (clean architecture). **GPL v3** (derivative of Simon Adlem, G7RZU’s original proxy).

### Why it ships with the monitor (not inside the peer server)

There is no single mandatory layout for every deployment, but **today the proxy lives in the adn-monitor repo** on purpose:

- **Same config and ops** as the dashboard stack: **`adn-mon.yaml`**, **`ADN_CONFIG_PATH`**, and usually the same host as **PHP** and **MySQL**.
- **Self-service** ( **`Clients`**, RPTO, **`modified`**) is built around that ecosystem; the peer server binary does not own that database or the **`PROXY`** block.
- **Role split:** the **ADN DMR Peer Server** is the **radio core** (HBP/OpenBridge, bridges, voice, TCP reports). The hotspot proxy is an **optional UDP front** toward a MASTER that already listens on a port **range** — useful when many hotspots share one public address.

**Bundling the proxy into the peer server** (one binary, one `adn-server.yaml`) is conceivable for packaging, but it implies **merging configuration**, **rethinking self-service wiring**, and extra maintenance — only worth it if you explicitly want a single deployable “all-in-one” server.

---

## Configuration file (same as monitor)

The proxy does **not** use `adn-server.yaml`. It reads the **monitor** YAML:

| Source | Purpose |
|--------|---------|
| **`ADN_CONFIG_PATH`** | Environment variable: absolute path to **`adn-mon.yaml`** (shared with **monitor**, **PHP backend**, optional **`.env`** in repo root). |
| **`python proxy/proxy.py --config /path/to/adn-mon.yaml`** | Overrides the path for this process only. |
| **Default** (if unset) | `../monitor/adn-mon.yaml` relative to the `proxy/` directory when run from the adn-monitor tree. |

Sections used:

- **`PROXY`** — listen address, master host, destination port **range**, timeouts, debug, block lists.
- **`SELF_SERVICE`** — MySQL and **`USE_SELFSERVICE`** (for **`Clients`** table, RPTO / options).
- **`LOGGER`** — **`LOG_PATH`** and **`PROXY_LOG_FILE`** (proxy log is separate from **`LOG_FILE`** used by `monitor.py`).

Optional **environment** overrides (see `proxy/README.md` in the repo): e.g. **`ADN_PROXY_DEBUG`**, **`ADN_PROXY_LISTENPORT`**.

---

## `PROXY` keys (`adn-mon.yaml`)

| Key | Role |
|-----|------|
| **MASTER** | IP or **hostname** of the **ADN DMR Peer Server** host. Resolved to an IPv4 address at startup (Twisted requires an IP for `write()`). |
| **LISTEN_PORT** | UDP port where **hotspots** connect **to the proxy** (the address users configure on the hotspot). |
| **LISTEN_IP** | Empty often means all interfaces; otherwise bind to this address. |
| **DESTPORT_START** / **DEST_PORT_END** | Inclusive range of UDP ports on **`MASTER`** used **one per proxied hotspot** (sequential allocation inside the proxy). |
| **TIMEOUT** | Idle / session timeout (seconds). |
| **STATS** | Extra statistics logging. |
| **DEBUG** | Verbose packet logging (or use **`ADN_PROXY_DEBUG=1`**). |
| **CLIENT_INFO** | Per-client info in logs. |
| **BLACK_LIST** / **IP_BLACK_LIST** | Block radio IDs or source IPs. |

Internal config keys (after load) use mixed-case names (`Master`, `ListenPort`, …) — see `adn_proxy.infrastructure.config_loader`.

---

## Peer server (`adn-server.yaml`) must cover the port range

The proxy forwards traffic to **`MASTER:DESTPORT`** for each client, where **DESTPORT** is chosen inside **[DESTPORT_START, DEST_PORT_END]**.

The **ADN DMR Peer Server** must therefore **listen on UDP** on **that host** for **every port** in the range that you intend to use (one **MASTER** listener per port, or equivalent).

- A **single** `MODE: MASTER` with **one** `PORT` is **not** enough for multiple proxy clients if they map to different **DESTPORT** values — you need **multiple listeners** on the range.
- Typical approaches: **`GENERATOR`** on a MASTER system (splits into `NAME-0`, `NAME-1`, … with consecutive **PORT** values — see [Server configuration](../server/user-guide/configuration.md)), and/or multiple **`SYSTEMS`** entries, aligned with **`DESTPORT_START`…`DEST_PORT_END`** in **`PROXY`**.

If the server only listens on e.g. **56400** but the proxy sends to **56401**, that client will not register.

---

## How the process starts

1. Resolve config path (`ADN_CONFIG_PATH`, `--config`, or default).
2. **`load_config()`** parses YAML → **`PROXY`**, **`SELF_SERVICE`**, **`LOG`**.
3. Optional **MySQL** pool if self-service / DB features are enabled.
4. Twisted **reactor** runs UDP **ProxyProtocol** on **`LISTEN_IP:LISTEN_PORT`**, forwarding to **`MASTER:assigned_dest_port`**.

Run (from adn-monitor root, with env set):

```bash
export ADN_CONFIG_PATH=/opt/adn-monitor/monitor/adn-mon.yaml
python proxy/proxy.py
# or
python proxy/proxy.py --config /path/to/adn-mon.yaml
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

Hotspots appear on the dashboard only if the **peer server** sends **TCP reports** to the same host/port as **`ADN_CONNECTION`** in **`adn-mon.yaml`**. Align **`REPORTS`** on the server with **`ADN_IP` / `ADN_PORT`**. See [Monitoring and reports](../server/user-guide/monitoring.md).

---

## See also

- [Monitor configuration](configuration.md) — full **`adn-mon.yaml`** reference (PROXY section summary).
- [Architecture](architecture.md) — where the proxy sits in the stack.
- [Self-service](self-service.md) — DB, **`modified`**, RPTO timing.
