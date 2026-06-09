# Parrot (playback)

## What it is

**Parrot** records incoming **group** voice and plays it back (echo / parrot). It runs as a **PEER** that connects to the **ECHO** master on the main peer server (TG 9990 bridge).

The playback runtime is part of **`adn-server`**; run **`adn-server.py --parrot`** with minimal **`adn-parrot.yaml`**.

## Configuration

Use a **small separate YAML** — only what the PEER needs to attach to **ECHO** in `adn-server.yaml`:

| Field | Role |
|-------|------|
| `GLOBAL.SERVER_ID` | Parrot network identity (often `9990`) |
| `LOGGER` | Log file (optional but recommended) |
| `SYSTEMS.PARROT` | `MODE: PEER`, local `IP`/`PORT`, `MASTER_IP`/`MASTER_PORT`, `PASSPHRASE`, `RADIO_ID`, `CALLSIGN`, `OPTIONS` |

No `PROXY`, `ALIASES`, or `REPORTS` required. **`MASTER_PORT`** and **`PASSPHRASE`** must match **`ECHO`** on the main server.

- Copy **`adn-parrot.example.yaml`** → **`adn-parrot.yaml`** (not committed).
- Run:

```bash
python adn-server.py --parrot -c adn-parrot.yaml
```

Typical production: separate **systemd** unit (see `examples/systemd/adn-parrot.service` in the repo), same binary:

```bash
sudo cp examples/systemd/adn-parrot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adn-parrot
```

## Relation to TG 9990 / ECHO

The main server may expose an **ECHO** bridge on **TG 9990** for in-band echo. **Parrot** is a **standalone** service with its own config — use one or the other according to your deployment.

## Documentation

This page is the summary shipped with the repository; extend your deployment notes locally as needed.
