# Echo (playback)

## What it is

**Echo** records incoming **group** voice and plays it back on TG **9990**. It runs as a **PEER** process that connects to the **ECHO** master on the main peer server (TG 9990 bridge).

The playback runtime is part of **`adn-server`**; run **`adn-server.py --echo`** with minimal **`adn-echo.yaml`**.

## Configuration

Use a **small separate YAML** — only what the PEER needs to attach to **ECHO** in `adn-server.yaml`:

| Field | Role |
|-------|------|
| `GLOBAL.SERVER_ID` | Echo network identity (often `9990`) |
| `LOGGER` | Log file (optional but recommended) |
| `SYSTEMS.ECHO` | `MODE: PEER`, local `IP`/`PORT`, `MASTER_IP`/`MASTER_PORT`, `PASSPHRASE`, `RADIO_ID`, `CALLSIGN`, `OPTIONS` |

No `PROXY`, `ALIASES`, or `REPORTS` required. **`MASTER_PORT`** and **`PASSPHRASE`** must match **`ECHO`** on the main server.

- Copy **`adn-echo.example.yaml`** → **`adn-echo.yaml`** (not committed).
- Run:

```bash
python adn-server.py --echo -c adn-echo.yaml
```

Typical production: separate **systemd** unit (see `examples/systemd/adn-echo.service` in the repo), same binary:

```bash
sudo cp examples/systemd/adn-echo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adn-echo
```

## Relation to TG 9990

The main server exposes an **ECHO** master on **TG 9990** for the echo bridge. The standalone **echo** service is a separate process with its own config that connects to that master.

## Multi-hotspot behaviour (inject-only proxy)

When hotspots attach through the **integrated proxy** (`PROXY`), several radios
may share the same MASTER as peers. In legacy `adn-dmr-server` each MASTER had
a single peer, so echo naturally returned only to the caller. The multi-peer
inject-only proxy enforces the same explicitly:

- **Point-to-point delivery.** Echo playback (TG 9990) and on-demand service
  TGs (**9991–9999**) are delivered **only** to the exact peer that originated
  the call (`RX_PEER` on the active slot), **never** to other hotspots of the
  same user. There is no fuzzy matching on the source DMR ID.
- **Single-peer fallback.** When only one peer is connected, the packet is
  delivered to it (legacy single-peer behaviour).
- This applies to both the **data plane** (audio routing) and the **report
  plane** (`BRDG_EVENT` sent to the monitor): the monitor shows the echo chip
  on the originating hotspot, not on a sibling.

See [Voice routing and contention — Downlink gate](../development/routing-and-contention.md#downlink-gate-does-a-peer-receive-the-packet)
and [Hotspot proxy — Multi-hotspot behaviour](hotspot-proxy.md#multi-hotspot-behaviour).

## Documentation

This page is the summary shipped with the repository; extend your deployment notes locally as needed.
