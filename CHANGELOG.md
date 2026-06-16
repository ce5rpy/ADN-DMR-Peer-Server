# Changelog

All notable changes to **adn-server** are documented here.

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
