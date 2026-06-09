# Arquitectura (capas limpias)

## Capas

1. **Dominio** (`src/adn_server/domain/`) — entidades, objetos de valor, errores, `Result`. Sin E/S, sin Twisted.
2. **Aplicación** (`src/adn_server/application/`) — casos de uso (`BridgeUseCases`, `VoiceUseCases`, …) y **ports** (interfaces).
3. **Infraestructura** (`src/adn_server/infrastructure/`) — config YAML, Twisted UDP/TCP, voz, persistencia, adaptadores de seguridad.

**Regla de dependencias:** infraestructura → aplicación → dominio (solo hacia dentro).

## Punto de entrada

`main.py` cablea configuración, temporizadores **LoopingCall**, fábricas para **HBPProtocol**, servidor de informes e inyecta casos de uso.

## Dónde leer código

| Tema | Ubicación |
|------|-----------|
| Enrutado de bridge, `dmrd_received`, bucle OpenBridge | `application/bridge_use_cases.py` |
| HBP / OpenBridge UDP | `infrastructure/twisted_adapters/udp_hbp.py` |
| Informes TCP | `infrastructure/twisted_adapters/report_server.py` (fábrica), eventos de bridge desde casos de uso |
| Voz / TTS | `application/voice_use_cases.py`, `infrastructure/voice/` |
| Proxy hotspot (fan-in) | `infrastructure/proxy/` (`udp_fanin.py`, `runtime.py`), casos de uso en `application/proxy/` |
| Self-service (MySQL) | `infrastructure/proxy/self_service_bridge.py`, `infrastructure/proxy/persistence/` |

## Configuración como estado compartido

Un **`config` dict** mutable se pasa por adaptadores; actualizaciones en tiempo de ejecución (opciones, `SUB_MAP`, `_bcsq` OpenBridge) permanecen visibles globalmente durante la vida del proceso.
