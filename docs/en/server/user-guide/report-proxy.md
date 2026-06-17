# Report proxy (legacy dashboards)

**ADN DMR Peer Server 2.x** emits **report wire v2** (JSON over TCP). **adn-monitor 2.x** understands that protocol and connects **directly** to the server — no extra component is required.

Some **legacy dashboard stacks** still ship their own `dashboard.py` / `monitor.py` backend and speak **report wire v1** only (pickled `CONFIG_SND` / `BRIDGE_SND`, CSV `BRDG_EVENT`). Those monitors **cannot** connect to **adn-server 2.x** on the report port.

The optional **[ADN-report-proxy](https://github.com/ce5rpy/ADN-report-proxy)** package sits between the two: it connects **upstream** to the real server (v2), listens **downstream** where the legacy monitor expects the server (v1), and translates **v2 → v1**.

| Stack | Upstream server | Works without proxy? |
|-------|-----------------|----------------------|
| **adn-monitor 2.x** (React) | **adn-server 2.x** | Yes — connect to `REPORTS.REPORT_PORT` |
| Legacy dashboard + bundled monitor (v1) | **adn-dmr-server** (v1) | Yes — direct to server report port |
| Legacy dashboard + bundled monitor (v1) | **adn-server 2.x** (v2) | **No** — use **report-proxy** |

Typical legacy targets: old **ADN-Dashboard** forks, **HBMonitor** / **FDMR Monitor** deployments that still run a Python monitor process against `dashboard.cfg` / `monitor.cfg`.

## Topology

```text
┌───────────────────┐
│    adn-server     │
│   LISTENS :4321   │
└─────────▲─────────┘
          │
          │  TCP v2 JSON
          │  (report-proxy is CLIENT)
          │
┌─────────┴─────────┐
│   report-proxy    │
│   LISTENS :4322   │
└─────────▲─────────┘
          │
          │  TCP v1 pickle
          │  (legacy dashboard is CLIENT)
          │
┌─────────┴─────────┐
│ legacy dashboard  │
│    monitor.py     │
└───────────────────┘
```

| Component | Role | Default port | Config | Key setting |
|-----------|------|--------------|--------|-------------|
| **adn-server** | Listens for report clients | **4321** | `adn-server.yaml` | `REPORTS.REPORT_PORT` |
| **report-proxy** | Connects to the server | 4321 | `report-proxy.yaml` | `UPSTREAM.PORT` |
| **report-proxy** | Listens for the legacy monitor | **4322** | `report-proxy.yaml` | `LISTEN.PORT` |
| **Legacy dashboard** | Connects to the proxy | **4322** | `dashboard.cfg` | `SERVER_PORT` |

**Do not** point the legacy dashboard at **4321** — that is the server’s v2 port.

**Do not** set `UPSTREAM.PORT` to **4322** — that is the proxy’s own listen port.

## Server side (`adn-server.yaml`)

Reporting must be enabled and the **proxy host IP** must be in the allow list:

```yaml
REPORTS:
  REPORT: true
  REPORT_INTERVAL: 60
  REPORT_PORT: 4321
  REPORT_CLIENTS: "127.0.0.1"   # IP of the machine running report-proxy
```

If the proxy runs on another host, use **that host’s IP** in `REPORT_CLIENTS`, not only `127.0.0.1`. See [Configuration](configuration.md#reports) for all `REPORTS` keys.

## Proxy and legacy dashboard

Install and run the proxy from the **[ADN-report-proxy](https://github.com/ce5rpy/ADN-report-proxy)** repository (`report-proxy.yaml`, `python3 report-proxy.py -c report-proxy.yaml`). Point `UPSTREAM` at the server’s `REPORT_PORT` and `LISTEN` at the port the legacy monitor uses (often **4322**).

In legacy `dashboard.cfg` / `monitor.cfg`:

```ini
[SERVER CONNECTION]
SERVER_IP = 127.0.0.1
SERVER_PORT = 4322
```

`SERVER_IP` is the host where **report-proxy** listens, not necessarily the adn-server host.

**Start order:** adn-server → report-proxy → legacy monitor backend.

Full step-by-step, multi-host examples, verification checks, and common mistakes: **[ADN-report-proxy README](https://github.com/ce5rpy/ADN-report-proxy#configuration-legacy-dashboard--adn-server-2x)**.

## Wire translation (summary)

| Upstream (v2 from adn-server) | Downstream (v1 to legacy monitor) |
|--------------------------------|-----------------------------------|
| `HELLO` (`report_protocol: 2`) | `HELLO` (`protocol: 1`) |
| `STATE_SND` / `dashboard_state` | `CONFIG_SND` (pickle) |
| `ROUTING_TABLE_SND` | `BRIDGE_SND` (pickle) |
| `TOPOLOGY_SND` | `CONFIG_SND` (pickle) |
| `VOICE_EVENT_SND` | `BRDG_EVENT` (CSV) |

Schema detail for v2: [Report protocol v2 (JSON)](../protocols/report-v2.md).

## See also

- [Monitoring and reports](monitoring.md) — report channel, **adn-monitor** pairing, log lines.
- [ADN Monitor overview](../../monitor/index.md) — preferred dashboard for **adn-server 2.x** (no proxy).
