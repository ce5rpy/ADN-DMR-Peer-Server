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

## Documentation

This page is the summary shipped with the repository; extend your deployment notes locally as needed.
