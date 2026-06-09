# Introduction

## Purpose

This service is a **DMR peer and bridge**. It implements:

- **HBP** over UDP to **MASTER** and **PEER** systems (DMRD frames, authentication, pings).
- **OpenBridge** over UDP to other networks — **DMRE v5** (embedded version 5, BLAKE2b, hops) is the **recommended** inter-server mode on ADN; **DMRD** v1 remains available for compatibility (see [OpenBridge](../protocols/openbridge.md#dmre-and-openbridge-v5)).

Configuration is **YAML** (`adn-server.yaml`), merged at runtime with optional voice settings (`adn-voice.yaml`). The shipped template is `adn-server.example.yaml`.

## Design

Routing, timers, OpenBridge loop control, and protocol handling are implemented in **application** and **infrastructure** modules behind stable **ports**; the **domain** layer holds types and rules without I/O. This keeps the system easier to reason about and extend.

## Major subsystems

| Subsystem | Role |
|-----------|------|
| **Bridge router** | `BRIDGES` table: which systems forward which TG on which slot; dynamic bridges; static/stat bridges. |
| **HBP protocol** | Authentication, DMRD ingress/egress, repeat to peers, TG filters. |
| **OpenBridge** | DMRE ingress, hop limit, loop control (`min(1ST)`), BCSQ/BCKA when enabled. |
| **Voice** | AMBE files, scheduled announcements, TTS pipeline, on-demand playback (TG 9991–9999). |
| **Reporting** | TCP netstring channel to **adn-monitor** (and compatible dashboards): config, bridge state, call events (report v2 JSON). |
| **Hotspot proxy** | Optional integrated UDP fan-in (`PROXY` in `adn-server.yaml`) plus MySQL **self-service** (`SELF_SERVICE`) for dashboard-driven hotspot options. |

## Related programs

- **Parrot / playback** — separate entrypoint (`adn-parrot.py`) for record-and-playback; see [Parrot](parrot.md).
- **Standalone hotspot proxy** — legacy `adn-proxy` in the **adn-monitor** repo when not using the integrated proxy; see [Hotspot proxy (standalone)](../../monitor/hotspot-proxy.md).

## Next steps

- [Configuration](configuration.md) — files, `GLOBAL`, **MASTER** / **PEER** / **OPENBRIDGE**, ACLs, reports, **`PROXY`**, **`SELF_SERVICE`**, aliases, voice merge.
- [Bridges and talkgroups](bridges-and-talkgroups.md) — how `BRIDGES` works.
- [Special numbers](special-numbers.md) — TG 4000, information services, echo.
- [Hotspot proxy](hotspot-proxy.md) — integrated **`PROXY`** / **`SELF_SERVICE`** in `adn-server.yaml`.
- [ADN Monitor](../../monitor/index.md) — dashboard, `adn-monitor.yaml`, self-service UI (separate repo, deployed with the server).
- [Credits & license](attribution.md) — ADN → FreeDMR → hblink3, license.
