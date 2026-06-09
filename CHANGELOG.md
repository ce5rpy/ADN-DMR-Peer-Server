# Changelog

All notable changes to **adn-server** are documented here. Versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Changed

- Parrot: integrated in `adn-server.py --parrot`; minimal `adn-parrot.yaml` (PEER → ECHO MASTER).

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
