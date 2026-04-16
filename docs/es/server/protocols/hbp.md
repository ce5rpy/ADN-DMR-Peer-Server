# HBP (HomeBrew Protocol) — DMRD

## Rol

**HBP** es el encapsulado UDP entre este servidor y sistemas **MASTER** / **PEER**. Las cargas usan el opcode **`DMRD`** (cuatro bytes ASCII) seguido de campos de voz/datos DMR (fuente RF, destino, ID de flujo, bloque AMBE, etc.).

## Autenticación

- Lado **MASTER**: RPTL → salt → RPTK → config; opciones de peer (**RPTO**) refrescan opciones del bridge.
- Lado **PEER**: conecta aguas arriba, repite autenticación, pings de mantenimiento.

Implementación: `infrastructure/twisted_adapters/udp_hbp.py` (`HBPProtocol`).

## OpenBridge frente a HBP

OpenBridge usa **`DMRD`** v1 (HMAC-SHA1) o **`DMRE`** (extendido); ver [OpenBridge](openbridge.md). Los enlaces HBP **MASTER/PEER** usan reglas clásicas **DMRD**.

## BER / RSSI

Para fuentes que no son OpenBridge, bytes opcionales **BER/RSSI** pueden añadirse tras la carga de voz de 53 bytes en ingreso; el reenvío a OpenBridge puede recortar o conservar campos según destino y reglas `to_target`.
