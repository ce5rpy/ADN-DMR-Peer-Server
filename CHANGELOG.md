# Changelog

All notable changes to **adn-server** are documented here.

<!-- version list -->

## v2.1.0 (2026-06-22)

### Bug Fixes

- Allow same static TG on TS1 and TS2 for duplex routing
  ([`e7d3dab`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/e7d3dab4c07000fec92a384c87f892d2d22affa3))

- Inject-only contention, dynamic TG restore, and UA timer parity
  ([#24](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/24),
  [`c5cbdb2`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/c5cbdb233112841c547bbc2ac3b4dfe5ed26d51f))

- Inject-only slot contention, monitor events, and UA timer display
  ([#24](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/24),
  [`c5cbdb2`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/c5cbdb233112841c547bbc2ac3b4dfe5ed26d51f))

- Reject malformed peer OPTIONS for monitor and downlink
  ([`08c648f`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/08c648fdc208822274ce50d0f8d3a64447e2972a))

- Slot contention, simplex RF mode, and static TG dedup
  ([`1931682`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/1931682337da141bd342cf9a65bd79ae3e78fcd6))

### Documentation

- Document simplex downlink TS2 choice (MMDVMHost DMO parity)
  ([`49a9605`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/49a96055e93579870c38f7c7f152e17293f39406))

### Features

- Dynamic TG restore, OBP cross-slot downlink, and DB migration 005
  ([#24](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/24),
  [`c5cbdb2`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/c5cbdb233112841c547bbc2ac3b4dfe5ed26d51f))


## v2.0.6 (2026-06-22)

### Bug Fixes

- Tear down REPEAT and bridge TX per stream on concurrent duplex slots
  ([#19](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/19),
  [`de05504`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/de05504a700193706dbae2acc0892b26daff3482))

### Chores

- **ci**: Require merge-commit release PRs for develop ff sync
  ([#21](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/21),
  [`374cc68`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/374cc686efcdbae314e8b67d125032a0b1d22722))


## v2.0.5 (2026-06-21)

### Bug Fixes

- Cross-slot DMRD remap and monitor TE slot
  ([#18](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/18),
  [`5945d66`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/5945d6641b4056a77b678093f5fead8491263eb4))

- Remap REPEAT DMRD slot to peer OPTIONS for cross-slot downlink
  ([#18](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/18),
  [`5945d66`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/5945d6641b4056a77b678093f5fead8491263eb4))

- Restore cross-slot downlink and REPEAT monitor activity
  ([#18](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/18),
  [`5945d66`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/5945d6641b4056a77b678093f5fead8491263eb4))

### Chores

- **ci**: Sync develop via merge instead of force-push
  ([#18](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/18),
  [`5945d66`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/5945d6641b4056a77b678093f5fead8491263eb4))


## v2.0.4 (2026-06-21)

### Bug Fixes

- Cross-slot downlink and REPEAT monitor activity
  ([`f561b26`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/f561b2685c53b8625b87ce73d599c0276fba8fa1))

### Chores

- **ci**: Sync develop via merge after release
  ([`e05dc00`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/e05dc003185b49522d0838ed33c8074303f3600c))


## v2.0.3 (2026-06-21)

### Bug Fixes

- **ci**: Force-with-lease when syncing develop after release
  ([#13](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/13),
  [`5fad3b5`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/5fad3b515fe17ca94f33b49f540956ea0e2ae178))


## v2.0.2 (2026-06-21)

### Bug Fixes

- Keep YAML SINGLE_MODE on multi-peer masters for dynamic TGs
  ([#12](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/12),
  [`47c7e33`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/47c7e33c7adc98abc6134547f0539f6cd9f54b59))

- SINGLE=0 multi-dynamic TGs and YAML SINGLE_MODE defaults
  ([#12](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/12),
  [`47c7e33`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/47c7e33c7adc98abc6134547f0539f6cd9f54b59))

### Chores

- Run releases on master only, not develop
  ([#12](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/12),
  [`47c7e33`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/47c7e33c7adc98abc6134547f0539f6cd9f54b59))


## v2.0.1 (2026-06-20)

### Bug Fixes

- Filter standalone DMRA downlink by TG subscription
  ([#10](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/10),
  [`0dcdf54`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/0dcdf54a07328f7203b02809cd7e26255987258e))

### Chores

- Run releases on master only, not develop
  ([#10](https://github.com/ce5rpy/ADN-DMR-Peer-Server/pull/10),
  [`0dcdf54`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/0dcdf54a07328f7203b02809cd7e26255987258e))


## v2.0.0 (2026-06-19)

### Chores

- Add release workflow and semver versioning (semver from 2.0.0; no RC phase)
  ([`013b766`](https://github.com/ce5rpy/ADN-DMR-Peer-Server/commit/013b766a30dca0128daf35c116385cf234410b99))


## [2.0.0-rc.4] - 2026-06-18

### Added

- **Docs (MkDocs EN/ES):** bridges vs subscriptions, performance notes, report-proxy guide for legacy dashboards, Mermaid diagrams in architecture/monitoring pages.

### Fixed

- **Echo TG 9990** — excluded from SINGLE/UA session locks; inject-only monitor remap for echo TX legs; bridge TX report field 5 resolves hotspot radio id for ECHO/hotspot live chips.
- **Dynamic TG restore** — `sync_restored_dynamic_tgs` passes `now=` as keyword (fixes TypeError on echo startup after DB restore).

### Compatibility

- **Monitor:** adn-monitor **2.0.0-rc.5**.

## [2.0.0-rc.3] - 2026-06-17

### Added

- **Dynamic TG persistence** — per-peer user-activated TGs stored in MariaDB (`peer_dynamic_tgs`); restored on hotspot reconnect (RPTC); shared `DATABASE` block with proxy self-service.
- **Server-owned migration** — ensures `peer_dynamic_tgs` table on startup (idempotent, same schema as adn-monitor `004`).

### Fixed

- **TG 4000** — clears all peer dynamic slots (memory + DB); emits `INGRESS` BRDG_EVENT so monitor SINGLE=0 chips clear without stuck TX; TG 4000 is never stored as a UA session.

### Compatibility

- **Monitor:** adn-monitor **2.0.0-rc.4**.

## [2.0.0-rc.2] - 2026-06-16

### Fixed

- **Cross-slot static TG downlink** (legacy REPEAT parity): inject-only MASTER delivers group voice to hotspots when the TG is listed in TS1 or TS2 OPTIONS, regardless of incoming wire timeslot. Wire slot is unchanged; downlink index and `peer_should_receive_group_voice` match both OPTIONS lists.

### Compatibility

- **Monitor:** adn-monitor **2.0.0-rc.2** (TS chip maps OPTIONS static slot on receive).

## [2.0.0-rc.1] - 2026-06-12

First v2 release candidate since **1.0.0** (~70 commits). HBP/OpenBridge on-wire behaviour preserved.

### Added

- **Report v2** — JSON HELLO, slim `dashboard_state` TCP wire (no full topology/routing snapshots to monitor), bounded report queue, optional MQTT.
- **Unified binary** — `adn-server.py` with `--echo`, `--doctor`, `--no-proxy`; wiring in `bootstrap/peer_server.py`.
- **Integrated proxy** — in-process UDP fan-in (`PROXY`), inject-only MASTER, self-service MySQL OPTIONS, peer blacklist/timers parity with legacy proxy.
- **Subscription routing** — `SubscriptionStore` + `SubscriptionRouter` as runtime authority; store-native timers, OPTIONS/static TG, in-band ON/OFF; `MeshCodecRegistry` on OpenBridge.
- **Inject-only production path** — per-peer OPTIONS downlink filter, monitor topology expansion (virtual SYSTEM slots), CONFIG push on peer connect.
- **Performance** — O(1) BRIDGES source index; peer downlink index for inject fan-out; adaptive CONFIG_SND debounce on mass login.

### Changed

- **Architecture** — `bridge_use_cases` split into `routing_use_cases` + mixins; `RuntimeContext` and atomic SIGHUP reload; DMR codecs vendored to `domain/dmr/`; mesh codecs extracted from `udp_hbp`.
- **OPTIONS / static TG** — event-driven refresh (RPTO, startup, reload, dmrd fallback) instead of 26 s periodic loop.
- **Talker Alias** — embed on local REPEAT; passthrough and dedupe fixes on relay path.

### Fixed

- OpenBridge packet control and rate-limit parity with legacy.
- Echo playback when sequence byte wraps; echo TG 9990 bootstrap.
- Inject TG 4000: clear dynamics once per PTT per peer.
- Unit data (ARS/LRRP) downlink for 7-digit private calls; monitor TS chip (no spurious `PRIVATE VOICE` on unit data).
- OBP → HBP voice forwarding and downlink CPU under multi-peer inject load.

### Removed

- Standalone **`adn-parrot.py`** — use `adn-server.py --echo`.
- Periodic **26 s `options_config_loop`**.
- Legacy pickle CONFIG/BRIDGE snapshots on the **server → monitor** wire (monitor uses v2 slim ingest).

### Compatibility

- **Monitor:** adn-monitor **2.0.0-rc.1** (report v2 slim wire, HELLO JSON).
- **Wire:** HBP and OpenBridge on-wire formats unchanged vs legacy ADN DMR Server.
- **Config:** same `adn-server.yaml` shape; add optional `PROXY` / `SELF_SERVICE` / `REPORTS.MQTT` sections.

## [1.0.0] - 2026-06-06

First stable public release. 

### Added

- Clean-architecture rewrite: domain, application, infrastructure layers.
- YAML configuration (`adn-server.yaml`) with startup validation.
- HBP MASTER/PEER and OpenBridge forwarding with legacy parity (loops, BCSQ, packet control).
- Talker Alias: DMRA packets and embedded LC overlay (UTF-8 / ISO-8859-1 / 7-bit formats).
- Voice: announcements, TTS pipeline, on-demand AMBE playback, recording.
- Echo playback entrypoint (`adn-server.py --echo`, `adn-echo.yaml`) for TG 9990.
- Monitor report TCP: HELLO JSON (mode v2), CONFIG_SND / BRIDGE_SND (pickle), BRDG_EVENT.
- Hot reload: `adn-server.yaml` (SIGHUP), `adn-voice.yaml` (15 s loop), log reopen (SIGUSR2).
- MkDocs user guide (EN/ES).

### Fixed (highlights since parity baseline)

- OpenBridge packet control and ingress timing.
- Echo playback sequence preservation on long QSOs.
- Config validator accepts numeric MMDVM option fields in YAML.
- OBP END/TX reporting and STATUS lifecycle alignment with legacy.

### Compatibility

- **Monitor:** adn-monitor **1.0.0** (HELLO v2 + legacy pickle report).
- **Config:** use `adn-server.example.yaml` as template; production YAML is not committed.
- **Wire:** HBP and OpenBridge on-wire formats unchanged vs legacy ADN DMR Server.

[1.0.0]: https://github.com/ce5rpy/ADN-DMR-Peer-Server/releases/tag/v1.0.0
