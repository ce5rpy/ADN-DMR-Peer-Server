# Monitor e informes

## Canal TCP de informes

Cuando **`REPORTS`** está habilitado en la config del servidor, el **ADN DMR Peer Server** escucha en TCP y los **clientes de informes** (típicamente **adn-monitor**) se conectan y reciben:

- **CONFIG_SND** / **BRIDGE_SND** — instantáneas pickle de sistemas y bridges.
- **BRDG_EVENT** — eventos de texto para llamadas (`GROUP VOICE`, `PRIVATE VOICE`, etc.).

El **monitor** decodifica estos mensajes, actualiza **CTABLE** / **BTABLE** y (con MySQL configurado) persiste Last Heard / estadísticas.

**Pila completa:** [Descripción general del ADN Monitor](../../monitor/index.md) (monitor Python, WebSocket, API PHP, proxy y self-service opcionales).

## Semántica del monitor en OpenBridge

- **`GROUP VOICE,INGRESS,RX`** — primera aparición de un flujo en una pata OpenBridge (depuración; visibilidad completa en logs).
- **`GROUP VOICE,START,RX`** — inicio **canónico** tras **control de bucle** (alimenta chips del panel / CTABLE).
- **`GROUP VOICE,END,…`** — fin de llamada; variantes RX/TX según dirección.

El panel muestra el estado **operativo** desde **START** (canónico); el **log del Monitor** muestra **INGRESS** más **START** para depurar duplicados en malla.

## Requisitos

- Conectividad de red desde el **host del monitor** al **`REPORTS.REPORT_PORT`** del servidor (y la lista **`REPORT_CLIENTS`** del servidor debe incluir al monitor si se usa).
- **adn-monitor** `ADN_CONNECTION.ADN_IP` / **`ADN_PORT`** debe coincidir con el servidor — ver [Configuración del monitor](../../monitor/configuration.md#adn_connection).

## Self-service y hotspots

Los operadores que editan **opciones de dispositivo** desde el panel usan el flujo **self-service** (MySQL **`Clients`**, proxy **RPTO**). Está documentado en [Self-service](../../monitor/self-service.md); **no** forma parte solo del binario del peer server. Para la configuración del **proxy hotspot** (`PROXY` en `adn-mon.yaml`), enlace al rango **UDP** del peer server y arranque del proceso, ver [Proxy hotspot](../../monitor/hotspot-proxy.md).
