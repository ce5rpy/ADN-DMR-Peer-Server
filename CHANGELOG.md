# Changelog

All notable changes to **adn-server** are documented here. Versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Added

- P2-015 (in progress): store-native `rule_timer_loop` and `apply_in_band_signalling`.
- `InbandTriggers` (ON/OFF/RESET) on `Subscription` with import/export round-trip.
- `to_target` iterates `ForwardLeg` from `SubscriptionRouter.resolve()` instead of re-scanning BRIDGES rows.

### Changed

- `_export_store_to_router()` publishes store mutations without router→store overwrite (timer/in-band paths).

## [2.0.0-alpha.2] - 2026-06-11

Subscription runtime (phase 2b/2c) closed for production Chile.

### Added

- Subscription store always wired at runtime; `SubscriptionRouter` is the voice resolve path.
- `MeshCodecRegistry` on OpenBridge ingress/egress (phase 2c).

### Changed

- Removed YAML flags `USE_SUBSCRIPTION_ROUTER` and `USE_SUBSCRIPTION_STORE_AUTHORITY` (P2-014); rollback via git tags only.
- `get_bridges()` mirrors router state into the store before export (report/monitor shim).

### Fixed

- OBP → HBP voice: sync store before subscription resolve (`c10f7f8`).
- TG 4000: clear dynamics once per PTT, scoped to transmitting peer (inject-only).

## [2.0.0-alpha.1] - 2026-06-10

Phases 0–4 + 3b GA baseline (tag `v2.0.0-alpha1` alias retained).

### Added

- `adn-server.py --doctor` — validate config, UDP/TCP bind ports, PEER upstream and `MESH_PROTOCOL`.
- Integrated proxy fan-in, self-service MySQL OPTIONS, monitor slim report wire.

### Changed

- Parrot: integrated in `adn-server.py --parrot`; minimal `adn-parrot.yaml` (PEER → ECHO MASTER).
- Runtime wiring moved to `infrastructure/bootstrap/peer_server.py`; `main.py` is CLI-only (<200 lines).

### Removed

- **`adn-parrot.py`** and **`parrot_main.py`** — use `adn-server.py --parrot` instead.

## [1.0.0] - 2026-06-06

First stable public release. 

### Added

- Clean-architecture rewrite: domain, application, infrastructure layers.
- YAML configuration (`adn-server.yaml`) with startup validation.
- HBP MASTER/PEER and OpenBridge forwarding with legacy parity (loops, BCSQ, packet control).
- Talker Alias: DMRA packets and embedded LC overlay (UTF-8 / ISO-8859-1 / 7-bit formats).
- Voice: announcements, TTS pipeline, on-demand AMBE playback, recording.
- Parrot entrypoint (`adn-parrot.py`) for TG 9990 echo/playback.
- Monitor report TCP: HELLO JSON (mode v2), CONFIG_SND / BRIDGE_SND (pickle), BRDG_EVENT.
- Hot reload: `adn-server.yaml` (SIGHUP), `adn-voice.yaml` (15 s loop), log reopen (SIGUSR2).
- MkDocs user guide (EN/ES).

### Fixed (highlights since parity baseline)

- OpenBridge packet control and ingress timing.
- Parrot playback sequence preservation on long QSOs.
- Config validator accepts numeric MMDVM option fields in YAML.
- OBP END/TX reporting and STATUS lifecycle alignment with legacy.

### Compatibility

- **Monitor:** adn-monitor **1.0.0** (HELLO v2 + legacy pickle report).
- **Config:** use `adn-server.example.yaml` as template; production YAML is not committed.
- **Wire:** HBP and OpenBridge on-wire formats unchanged vs legacy ADN DMR Server.

[1.0.0]: https://github.com/ce5rpy/ADN-DMR-Peer-Server/releases/tag/v1.0.0
