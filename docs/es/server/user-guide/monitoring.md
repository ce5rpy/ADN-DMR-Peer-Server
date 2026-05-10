# Monitor e informes

## Canal TCP de informes

Cuando **`REPORTS`** está habilitado en la config del servidor, el **ADN DMR Peer Server** escucha en TCP y los **clientes de informes** (típicamente **adn-monitor**) se conectan y reciben:

- **HELLO** (opcode **`0xFF`**) — JSON enviado **el primero** en cada conexión TCP por **new-adn-server** (`adn-server`): nombre **`server`**, **`version`** del paquete, número de **`protocol`** y lista **`features`** (p. ej. `INGRESS`, `END_TX_FORWARD`, `PUSH_ON_CONNECT`). Permite al monitor marcar la sesión como **v2** antes de las cargas pickle.
- **CONFIG_SND** / **BRIDGE_SND** — instantáneas pickle de sistemas y bridges (tras HELLO al conectar, y de nuevo en actualizaciones / petición).
- **BRDG_EVENT** — eventos de texto para llamadas (`GROUP VOICE`, `PRIVATE VOICE`, etc.).

Las pilas antiguas (**legado** estilo `adn-dmr-server`) pueden **omitir** HELLO. **adn-monitor** espera hasta **`ADN_CONNECTION.HELLO_TIMEOUT_MS`** (ver [Configuración del monitor](../../monitor/configuration.md#adn_connection)); si no llega HELLO, asume informes **legacy**.

El **monitor** decodifica estos mensajes, actualiza **CTABLE** / **BTABLE** y (con MySQL configurado) persiste Last Heard / estadísticas.

**Pila completa:** [Descripción general del ADN Monitor](../../monitor/index.md) (monitor Python, WebSocket, API PHP, proxy y self-service opcionales).

### Líneas de log del canal de informes (logger `adn-monitor`)

Python usa el nombre de logger **`adn-monitor`** (ver **`LOGGER.LOG_FILE`** en `adn-monitor.yaml`). **INFO** típicos del cliente TCP de informes:

| Prefijo / texto del log | Significado |
|-------------------------|-------------|
| `(REPORT) Connection to report server established` | Sesión TCP activa; arranca la espera de HELLO (**`HELLO_TIMEOUT_MS`**). |
| `(REPORT) stringReceived: HELLO opcode=ff …` | Trama HELLO cruda en el cable. |
| `(REPORT) HELLO received: mode=v2 server=… version=… features=…` | JSON HELLO parseado; sesión **v2** (**new-adn-server**). |
| `(REPORT) No HELLO in …s; assuming legacy adn-dmr-server …` | No hay **`0xFF`** antes del timeout — modo **legacy** (solo CONFIG/BRIDGE pickle). Normal si el peer es **`adn-dmr-server`** clásico. Si **sabes** que el servidor es **new-adn-server** y aún ves esto, revisa **`ADN_IP`** / **`ADN_PORT`**, **`REPORTS.REPORT_CLIENTS`**, cortafuegos, o sube un poco **`HELLO_TIMEOUT_MS`** en enlaces muy lentos. |
| `(REPORT) CONFIG applied: …` / `(REPORT) BRIDGES applied: …` | Instantáneas pickle aplicadas a CTABLE/BTABLE. |

En **WARNING**: JSON HELLO inválido (`(REPORT) HELLO payload not valid JSON`), o **`Invalid GLOBAL.TIMEZONE`** si **`GLOBAL.TIMEZONE`** no es un nombre IANA válido.

## Semántica del monitor en OpenBridge

- **`GROUP VOICE,INGRESS,RX`** — primera aparición de un flujo en una pata OpenBridge (depuración; visibilidad completa en logs).
- **`GROUP VOICE,START,RX`** — inicio **canónico** tras **control de bucle** (alimenta chips del panel / CTABLE).
- **`GROUP VOICE,END,…`** — fin de llamada; variantes RX/TX según dirección.

El panel muestra el estado **operativo** desde **START** (canónico); el **log del Monitor** muestra **INGRESS** más **START** para depurar duplicados en malla.

## Requisitos

- Conectividad de red desde el **host del monitor** al **`REPORTS.REPORT_PORT`** del servidor (y la lista **`REPORT_CLIENTS`** del servidor debe incluir al monitor si se usa).
- **adn-monitor** `ADN_CONNECTION.ADN_IP` / **`ADN_PORT`** debe coincidir con el servidor — ver [Configuración del monitor](../../monitor/configuration.md#adn_connection).

## Self-service y hotspots

Los operadores que editan **opciones de dispositivo** desde el panel usan el flujo **self-service** (MySQL **`Clients`**, proxy **RPTO**). Está documentado en [Self-service](../../monitor/self-service.md); **no** forma parte solo del binario del peer server. Para la configuración del **proxy hotspot** (`PROXY` en **`adn-proxy.yaml`** por defecto), enlace al rango **UDP** del peer server y arranque del proceso, ver [Proxy hotspot](../../monitor/hotspot-proxy.md).
