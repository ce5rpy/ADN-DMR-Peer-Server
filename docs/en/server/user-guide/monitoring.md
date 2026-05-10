# Monitoring and reports

## TCP report channel

When **`REPORTS`** is enabled in the server config, the **ADN DMR Peer Server** listens on TCP and **report clients** (typically **adn-monitor**) connect and receive:

- **HELLO** (opcode **`0xFF`**) — JSON sent **first** on each new TCP connection by **new-adn-server** (`adn-server`): `server` name, package **`version`**, **`protocol`** number, and **`features`** (e.g. `INGRESS`, `END_TX_FORWARD`, `PUSH_ON_CONNECT`). Lets the monitor tag the session as **v2** before any pickled payloads.
- **CONFIG_SND** / **BRIDGE_SND** — pickled snapshots of systems and bridges (sent immediately after HELLO on connect, and again on updates / request).
- **BRDG_EVENT** — text events for calls (`GROUP VOICE`, `PRIVATE VOICE`, etc.).

Older stacks (**legacy** `adn-dmr-server`-style) may **omit** HELLO. **adn-monitor** waits up to **`ADN_CONNECTION.HELLO_TIMEOUT_MS`** (see [Monitor configuration](../../monitor/configuration.md#adn_connection)); if no HELLO arrives, it assumes **legacy** reporting.

The **monitor** decodes these messages, updates its **CTABLE** / **BTABLE**, and (when MySQL is configured) persists Last Heard / statistics.

**Full stack:** [ADN Monitor overview](../../monitor/index.md) (Python monitor, WebSocket, PHP API, optional proxy and self-service).

### Report channel log lines (`adn-monitor` logger)

Python uses the logger name **`adn-monitor`** (see **`LOGGER.LOG_FILE`** in `adn-monitor.yaml`). Typical **INFO** lines for the TCP report client:

| Log prefix / text | Meaning |
|-------------------|---------|
| `(REPORT) Connection to report server established` | TCP session up; HELLO wait timer starts (**`HELLO_TIMEOUT_MS`**). |
| `(REPORT) stringReceived: HELLO opcode=ff …` | Raw HELLO frame seen on the wire. |
| `(REPORT) HELLO received: mode=v2 server=… version=… features=…` | HELLO JSON parsed; session treated as **v2** (**new-adn-server**). |
| `(REPORT) No HELLO in …s; assuming legacy adn-dmr-server …` | No **`0xFF`** before timeout — monitor keeps **legacy** mode (pickled CONFIG/BRIDGE only). Expected if the peer is classic **`adn-dmr-server`**. If you **know** the server is **new-adn-server** but still see this, check **`ADN_IP`** / **`ADN_PORT`**, **`REPORTS.REPORT_CLIENTS`**, firewalls, or raise **`HELLO_TIMEOUT_MS`** slightly on very slow links. |
| `(REPORT) CONFIG applied: …` / `(REPORT) BRIDGES applied: …` | Pickled snapshots applied to CTABLE/BTABLE. |

At **WARNING**: invalid HELLO JSON (`(REPORT) HELLO payload not valid JSON`), or **`Invalid GLOBAL.TIMEZONE`** if **`GLOBAL.TIMEZONE`** in YAML is not a valid IANA name.

## OpenBridge monitor semantics

- **`GROUP VOICE,INGRESS,RX`** — first sight of a stream on an OpenBridge **leg** (debug; full visibility in logs).
- **`GROUP VOICE,START,RX`** — **canonical** start after **loop control** (feeds dashboard chips / CTABLE).
- **`GROUP VOICE,END,…`** — call end; RX/TX variants depending on direction.

The dashboard shows **operational** state from **START** (canonical); the **Monitor** log shows **INGRESS** plus **START** for troubleshooting mesh duplicates.

## Requirements

- Network reachability from the **monitor host** to the server’s **`REPORTS.REPORT_PORT`** (and the server’s **`REPORT_CLIENTS`** allow list must include the monitor if used).
- **adn-monitor** `ADN_CONNECTION.ADN_IP` / **`ADN_PORT`** must match the server — see [Monitor configuration](../../monitor/configuration.md#adn_connection).

## Self-service and hotspots

Operators editing **device options** from the dashboard use the **self-service** flow (MySQL **`Clients`**, proxy **RPTO**). That is documented under [Self-service](../../monitor/self-service.md); it is **not** part of the peer server binary alone. For **hotspot proxy** configuration (`PROXY` in **`adn-proxy.yaml`** by default), how it binds to the peer server **UDP port range**, and how the process starts, see [Hotspot proxy](../../monitor/hotspot-proxy.md).
