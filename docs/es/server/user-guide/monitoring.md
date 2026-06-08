# Monitor e informes

## Canal TCP de informes

Cuando **`REPORTS`** está habilitado en la config del servidor, el **ADN DMR Peer Server** escucha en TCP y los **clientes de informes** (típicamente **adn-monitor**) se conectan y reciben:

- **HELLO** (opcode **`0xFF`**) — JSON enviado **el primero** en cada conexión TCP por **ADN DMR Server** (`adn-server`): nombre **`server`**, **`version`** del paquete, número de **`protocol`** y lista **`features`** (p. ej. `INGRESS`, `END_TX_FORWARD`, `PUSH_ON_CONNECT`). Permite al monitor marcar la sesión como **v2** antes de las cargas pickle.
- **CONFIG_SND** / **BRIDGE_SND** — instantáneas pickle de sistemas y bridges (tras HELLO al conectar, en **`CONFIG_REQ`** / **`BRIDGE_REQ`**, en **reload** de config (**SIGHUP**), cuando un hotspot **MASTER** **registra o desconecta**, y en el bucle periódico **`REPORT_INTERVAL`**).
- **BRDG_EVENT** — eventos de texto para llamadas (`GROUP VOICE`, `PRIVATE VOICE`, etc.).

**Informes v2 (borrador):** mensajes JSON tipados (`topology`, `routing_table`, `voice_event`, `delta`) sustituirán pickle/CSV con `REPORTS.PROTOCOL: v2` (Fase 1). Esquema y wire: [Protocolo de informes v2 (JSON)](../protocols/report-v2.md).

Las pilas antiguas (**legado** estilo `adn-dmr-server`) pueden **omitir** HELLO. **adn-monitor** espera hasta **`ADN_CONNECTION.HELLO_TIMEOUT_MS`** (ver [Configuración del monitor](../../monitor/configuration.md#adn_connection)); si no llega HELLO, asume informes **legacy**.

El **monitor** decodifica estos mensajes, actualiza **CTABLE** / **BTABLE** y (con MySQL configurado) persiste Last Heard / estadísticas.

**Pila completa:** [Descripción general del ADN Monitor](../../monitor/index.md) (monitor Python, WebSocket, API PHP, proxy y self-service opcionales).

### Líneas de log del canal de informes (logger `adn-monitor`)

Python usa el nombre de logger **`adn-monitor`** (ver **`LOGGER.LOG_FILE`** en `adn-monitor.yaml`). **INFO** típicos del cliente TCP de informes:

| Prefijo / texto del log | Significado |
|-------------------------|-------------|
| `(REPORT) Connection to report server established` | Sesión TCP activa; arranca la espera de HELLO (**`HELLO_TIMEOUT_MS`**). |
| `(REPORT) stringReceived: HELLO opcode=ff …` | Trama HELLO cruda en el cable. |
| `(REPORT) HELLO received: mode=v2 server=… version=… features=…` | JSON HELLO parseado; sesión **v2** (**ADN DMR Server**). |
| `(REPORT) No HELLO in …s; assuming legacy adn-dmr-server …` | No hay **`0xFF`** antes del timeout — modo **legacy** (solo CONFIG/BRIDGE pickle). Normal si el peer es **`adn-dmr-server`** clásico. Si **sabes** que el servidor es **ADN DMR Server** y aún ves esto, revisa **`ADN_IP`** / **`ADN_PORT`**, **`REPORTS.REPORT_CLIENTS`**, cortafuegos, o sube un poco **`HELLO_TIMEOUT_MS`** en enlaces muy lentos. |
| `(REPORT) CONFIG applied: …` / `(REPORT) BRIDGES applied: …` | Instantáneas pickle aplicadas a CTABLE/BTABLE. |

En **WARNING**: JSON HELLO inválido (`(REPORT) HELLO payload not valid JSON`), o **`Invalid GLOBAL.TIMEZONE`** si **`GLOBAL.TIMEZONE`** no es un nombre IANA válido.

## Semántica del monitor en OpenBridge

- **`GROUP VOICE,INGRESS,RX`** — primera aparición de un flujo en una pata OpenBridge (depuración; visibilidad completa en logs).
- **`GROUP VOICE,START,RX`** — inicio **canónico** tras **control de bucle** (alimenta chips del panel / CTABLE).
- **`GROUP VOICE,END,…`** — fin de llamada; variantes RX/TX según dirección.

El panel muestra el estado **operativo** desde **START** (canónico); el **log del Monitor** muestra **INGRESS** más **START** para depurar duplicados en malla.

## Rotación de logs (logrotate)

Tras que **logrotate** renombre o mueva el fichero de log (patrón habitual: **`create`** — el fichero antiguo rota y aparece uno **nuevo vacío** en la ruta configurada), el proceso puede seguir con el descriptor abierto sobre el **inodo anterior**. Los logs parecen “no escribirse” en la ruta actual hasta que el proceso **reabra** los `FileHandler`.

**Recomendado:** usar **`create`** (evitar **`copytruncate`** si el servicio admite señal): **`copytruncate`** puede competir con escrituras concurrentes y **perder líneas**; **`WatchedFileHandler`** evita la señal pero tiene coste **por cada línea** de log.

Estos procesos tratan **`SIGUSR2`** solo para **reabrir** los ficheros de log (`logging.FileHandler`). **No recargan YAML**, bases de datos ni la configuración de Twisted.

| Proceso | Claves típicas de configuración |
|---------|-----------------------------------|
| **`adn-server`** / **`adn-parrot`** | **`LOGGER.LOG_FILE`** (ver `adn-server.example.yaml`) |
| **`adn-proxy`** | **`LOG.PATH`** + **`LOG.LOG_FILE`** en `adn-proxy.yaml` |
| **`adn-monitor`** | **`LOG.PATH`** + **`LOG.LOG_FILE`** en `adn-monitor.yaml` |

Ejemplo de fragmento en **`/etc/logrotate.d/adn`** (adaptar rutas y nombres de unidad):

```text
/var/log/adn-server/adn-server.log {
    weekly
    rotate 12
    compress
    delaycompress
    missingok
    notifempty
    create 0640 adn adn
    postrotate
        /bin/kill -USR2 "$(systemctl show adn-server.service -p MainPID --value)" 2>/dev/null || true
    endscript
}
```

Repite **`postrotate`** con **`kill -USR2`** para las unidades **`adn-parrot`**, **`adn-proxy`** y **`adn-monitor`** si rotas sus logs en el mismo host. Usa el **PID** correcto (**`MainPID`** de systemd, pidfile, o el proceso que gestiones).

## Requisitos

- Conectividad de red desde el **host del monitor** al **`REPORTS.REPORT_PORT`** del servidor (y la lista **`REPORT_CLIENTS`** del servidor debe incluir al monitor si se usa).
- **adn-monitor** `ADN_CONNECTION.ADN_IP` / **`ADN_PORT`** debe coincidir con el servidor — ver [Configuración del monitor](../../monitor/configuration.md#adn_connection).

## Self-service y hotspots

Los operadores que editan **opciones de dispositivo** desde el panel usan el flujo **self-service** (MySQL **`Clients`**, proxy **RPTO**). Está documentado en [Self-service](../../monitor/self-service.md); **no** forma parte solo del binario del peer server. Para la configuración del **proxy hotspot** (`PROXY` en **`adn-proxy.yaml`** por defecto), enlace al rango **UDP** del peer server y arranque del proceso, ver [Proxy hotspot](../../monitor/hotspot-proxy.md).
