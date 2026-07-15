# OBP proxy (single inbound port)

Optional `OBP_PROXY` stanza configures the fan-in listener for all `MODE: OPENBRIDGE` systems. When active, OpenBridge instances are **inject-only** (no per-bridge `listenUDP` in `HBPProtocol`); the proxy owns every inbound OBP socket.

## Activation

| YAML | Behaviour |
|------|-----------|
| No `OBP_PROXY` block, no OPENBRIDGE | N/A (proxy not started). |
| No `OBP_PROXY` block, OPENBRIDGE present | **Default proxy on** (`LISTEN_PORT` 62032, `BIND_LEGACY_PORTS` true). |
| `OBP_PROXY.ENABLED: false` | Legacy mode: each OPENBRIDGE binds its own `PORT`. |
| `OBP_PROXY.ENABLED: true` | Proxy manages all OBP inbound UDP (same as absent block). |

## Configuration

```yaml
OBP_PROXY:
  ENABLED: true
  LISTEN_PORT: 62032      # ADN standard OBP fan-in (pair to PROXY 62031)
  LISTEN_IP: ""           # optional bind address
  BIND_LEGACY_PORTS: true # default: also listen each SYSTEMS.*.PORT
  DEBUG: false
```

OPENBRIDGE sections stay unchanged (`PORT`, `NETWORK_ID`, `PASSPHRASE`, `TARGET_*`, ACL, etc.). With proxy enabled, `PORT` is kept as metadata (`_REPORT_PORT` internally) for monitor/report and optional legacy listeners.

## Per-bridge migration (`BIND_LEGACY_PORTS: true`)

When the global flag is true, each OPENBRIDGE can migrate individually:

| `SYSTEMS.*.PORT` | Behaviour |
|------------------|-----------|
| Same as `OBP_PROXY.LISTEN_PORT` (e.g. 62032) | Fan-in only for this bridge (no extra legacy listener). |
| Omitted, `0`, or empty | Same as `LISTEN_PORT` — fan-in only (migrated bridge). |
| Any other port (e.g. 62999) | Legacy listener stays open for that bridge. |

Example: migrate `OBP-CL2` to the shared fan-in while `OBP-EU` keeps `PORT: 62999`.

## Migration

1. Existing configs with OPENBRIDGE but no `OBP_PROXY` stanza already use defaults (`BIND_LEGACY_PORTS: true`) — no remote changes required.
2. Optionally add an explicit `OBP_PROXY` block to tune `LISTEN_PORT` / `BIND_LEGACY_PORTS`.
3. Set `BIND_LEGACY_PORTS: false` and close legacy ports when all remotes use `LISTEN_PORT`.

## Requirements

- `NETWORK_ID` must be unique among enabled OPENBRIDGE systems.
- `LISTEN_PORT` must not collide with any OPENBRIDGE `PORT` when `BIND_LEGACY_PORTS` is true.
- `RELAX_CHECKS: true` is recommended so `TARGET_SOCK` is learned from the first valid packet.

See also: [OpenBridge protocol](../protocols/openbridge.md).
