# Introducción

## Propósito

Este servicio es un **peer y bridge DMR**. Implementa:

- **HBP** por UDP hacia sistemas **MASTER** y **PEER** (tramas DMRD, autenticación, pings).
- **OpenBridge** por UDP hacia otras redes — **DMRE v5** (versión embebida 5, BLAKE2b, saltos) es el modo **recomendado** entre servidores en ADN; **DMRD** v1 sigue disponible para compatibilidad (ver [OpenBridge](../protocols/openbridge.md#dmre-and-openbridge-v5)).

La configuración es **YAML** (`adn-server.yaml`), fusionada en tiempo de ejecución con ajustes de voz opcionales (`adn-voice.yaml`). La plantilla incluida es `adn-server.example.yaml`.

## Diseño

Enrutado, temporizadores, control de bucle OpenBridge y manejo de protocolo están en módulos de **aplicación** e **infraestructura** detrás de **ports** estables; la capa de **dominio** contiene tipos y reglas sin E/S. Así el sistema es más fácil de seguir y extender.

## Subsistemas principales

| Subsistema | Rol |
|------------|-----|
| **Bridge router** | Tabla `BRIDGES`: qué sistemas reenvían qué TG en qué slot; bridges dinámicos; bridges estáticos/stat. |
| **Protocolo HBP** | Autenticación, ingreso/salida DMRD, repetición a peers, filtros TG. |
| **OpenBridge** | Ingreso DMRE, límite de saltos, control de bucle (`min(1ST)`), BCSQ/BCKA si están habilitados. |
| **Voz** | Ficheros AMBE, anuncios programados, tubería TTS, reproducción bajo demanda (TG 9991–9999). |
| **Informes** | Canal TCP netstring hacia **adn-monitor** (y paneles compatibles): config, estado de bridges, eventos de llamada (informe v2 JSON). |
| **Proxy hotspot** | Fan-in UDP integrado opcional (`PROXY` en `adn-server.yaml`) y **self-service** MySQL (`SELF_SERVICE`) para opciones de hotspot desde el panel. |

## Programas relacionados

- **Parrot / reproducción** — punto de entrada aparte (`adn-parrot.py`) para grabar y reproducir; ver [Parrot](parrot.md).
- **Proxy hotspot independiente** — **`adn-proxy`** legado en el repo **adn-monitor** si no usas el proxy integrado; ver [Proxy hotspot (independiente)](../../monitor/hotspot-proxy.md).

## Siguientes pasos

- [Configuración](configuration.md) — ficheros, `GLOBAL`, **MASTER** / **PEER** / **OPENBRIDGE**, ACL, informes, **`PROXY`**, **`SELF_SERVICE`**, alias, fusión de voz.
- [Bridges y talkgroups](bridges-and-talkgroups.md) — cómo funciona `BRIDGES`.
- [Números especiales](special-numbers.md) — TG 4000, servicios de información, eco.
- [Proxy hotspot](hotspot-proxy.md) — **`PROXY`** / **`SELF_SERVICE`** integrados en `adn-server.yaml`.
- [ADN Monitor](../../monitor/index.md) — panel, `adn-monitor.yaml`, UI self-service (repo aparte, desplegado con el servidor).
- [Créditos y licencia](attribution.md) — ADN → FreeDMR → hblink3, licencia.
