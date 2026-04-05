# Architecture (clean layering)

## Layers

1. **Domain** (`src/adn_server/domain/`) — entities, value objects, errors, `Result`. No I/O, no Twisted.
2. **Application** (`src/adn_server/application/`) — use cases (`BridgeUseCases`, `VoiceUseCases`, …) and **ports** (interfaces).
3. **Infrastructure** (`src/adn_server/infrastructure/`) — YAML config, Twisted UDP/TCP, voice, persistence, security adapters.

**Dependency rule:** infrastructure → application → domain (inward only).

## Entrypoint

`main.py` wires configuration, **LoopingCall** timers, factories for **HBPProtocol**, report client, and injects use cases.

## Where to read code

| Topic | Location |
|-------|----------|
| Bridge routing, `dmrd_received`, OpenBridge loop | `application/bridge_use_cases.py` |
| HBP / OpenBridge UDP | `infrastructure/twisted_adapters/udp_hbp.py` |
| Report TCP | `infrastructure/twisted_adapters/report_server.py` (factory), bridge events from use cases |
| Voice / TTS | `application/voice_use_cases.py`, `infrastructure/voice/` |

## Configuration as shared state

A **mutable `config` dict** is passed through adapters; runtime updates (options, `SUB_MAP`, OpenBridge `_bcsq`) remain visible globally for the lifetime of the process.
