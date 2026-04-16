# Proxy hotspot

El **proxy hotspot** forma parte del repositorio **adn-monitor**. Es un **relé UDP** entre **hotspots DMR** (Homebrew / HBP) y el **MASTER** del **ADN DMR Peer Server**: cada hotspot conectado se asigna a un **puerto de destino** dedicado en el host del peer server, de modo que muchos hotspots puedan compartir una IP pública sin choques de puertos.

Estructura: `proxy/proxy.py`, paquete `proxy/src/adn_proxy/` (arquitectura limpia). **GPL v3** (derivado del proxy original de Simon Adlem, G7RZU).

### Por qué va con el monitor (y no dentro del peer server) {#why-it-ships-with-the-monitor-not-inside-the-peer-server}

No hay un despliegue obligatorio único, pero **hoy el proxy vive en el repo adn-monitor** a propósito:

- **Misma config y operativa** que el panel: **`adn-mon.yaml`**, **`ADN_CONFIG_PATH`**, y normalmente el mismo host que **PHP** y **MySQL**.
- El **self-service** (**`Clients`**, RPTO, **`modified`**) está montado sobre ese ecosistema; el binario del peer server no posee esa base de datos ni el bloque **`PROXY`**.
- **División de roles:** el **ADN DMR Peer Server** es el **núcleo de radio** (HBP/OpenBridge, bridges, voz, informes TCP). El proxy hotspot es un **frente UDP opcional** hacia un MASTER que ya escucha en un **rango** de puertos — útil cuando muchos hotspots comparten una dirección pública.

**Integrar el proxy en el peer server** (un binario, un `adn-server.yaml`) es imaginable para empaquetado, pero implica **unificar configuración**, **replantear el cableado de self-service** y más mantenimiento — solo compensa si quieres explícitamente un servidor “todo en uno” desplegable.

---

## Fichero de configuración (igual que el monitor)

El proxy **no** usa `adn-server.yaml`. Lee el YAML del **monitor**:

| Origen | Uso |
|--------|-----|
| **`ADN_CONFIG_PATH`** | Variable de entorno: ruta absoluta a **`adn-mon.yaml`** (compartida con **monitor**, **backend PHP**, **`.env`** opcional en la raíz del repo). |
| **`python proxy/proxy.py --config /ruta/a/adn-mon.yaml`** | Sobrescribe la ruta solo para este proceso. |
| **Por defecto** (sin definir) | `../monitor/adn-mon.yaml` relativo al directorio `proxy/` al ejecutar desde el árbol adn-monitor. |

Secciones usadas:

- **`PROXY`** — dirección de escucha, host master, **rango** de puertos de destino, timeouts, debug, listas negras.
- **`SELF_SERVICE`** — MySQL y **`USE_SELFSERVICE`** (tabla **`Clients`**, RPTO / opciones).
- **`LOGGER`** — **`LOG_PATH`** y **`PROXY_LOG_FILE`** (log del proxy separado de **`LOG_FILE`** de `monitor.py`).

**Entorno** opcional (ver `proxy/README.md` en el repo): p. ej. **`ADN_PROXY_DEBUG`**, **`ADN_PROXY_LISTENPORT`**.

---

## Claves `PROXY` (`adn-mon.yaml`)

| Clave | Rol |
|-------|-----|
| **MASTER** | IP o **nombre de host** del **ADN DMR Peer Server**. Se resuelve a IPv4 al arrancar (Twisted necesita IP para `write()`). |
| **LISTEN_PORT** | Puerto UDP donde los **hotspots** se conectan **al proxy** (lo que configuran en el hotspot). |
| **LISTEN_IP** | Vacío suele significar todas las interfaces; si no, enlazar a esa dirección. |
| **DESTPORT_START** / **DEST_PORT_END** | Rango inclusivo de puertos UDP en **`MASTER`**, **uno por hotspot** proxy (asignación secuencial dentro del proxy). |
| **TIMEOUT** | Tiempo de inactividad / sesión (segundos). |
| **STATS** | Registro extra de estadísticas. |
| **DEBUG** | Log detallado de paquetes (o **`ADN_PROXY_DEBUG=1`**). |
| **CLIENT_INFO** | Información por cliente en logs. |
| **BLACK_LIST** / **IP_BLACK_LIST** | Bloquear IDs de radio o IPs de origen. |

Las claves internas tras la carga usan nombres mixtos (`Master`, `ListenPort`, …) — ver `adn_proxy.infrastructure.config_loader`.

---

## El peer server (`adn-server.yaml`) debe cubrir el rango de puertos

El proxy reenvía tráfico a **`MASTER:DESTPORT`** por cliente, con **DESTPORT** en **[DESTPORT_START, DEST_PORT_END]**.

El **ADN DMR Peer Server** debe **escuchar UDP** en **ese host** en **cada puerto** del rango que vayas a usar (un listener **MASTER** por puerto, o equivalente).

- Un único `MODE: MASTER` con un solo **`PORT`** **no** basta para varios clientes proxy si usan **DESTPORT** distintos — hacen falta **varios listeners** en el rango.
- Enfoques típicos: **`GENERATOR`** en un sistema MASTER (se parte en `NAME-0`, `NAME-1`, … con **PORT** consecutivos — ver [Configuración del servidor](../server/user-guide/configuration.md)), y/o varias entradas **`SYSTEMS`**, alineadas con **`DESTPORT_START`…`DEST_PORT_END`** en **`PROXY`**.

Si el servidor solo escucha p. ej. en **56400** pero el proxy envía a **56401**, ese cliente no se registrará.

---

## Cómo arranca el proceso

1. Resolver ruta de config (`ADN_CONFIG_PATH`, `--config`, o por defecto).
2. **`load_config()`** parsea YAML → **`PROXY`**, **`SELF_SERVICE`**, **`LOG`**.
3. Pool **MySQL** opcional si self-service / funciones de BD están activas.
4. El **reactor** Twisted ejecuta UDP **ProxyProtocol** en **`LISTEN_IP:LISTEN_PORT`**, reenviando a **`MASTER:puerto_destino_asignado`**.

Ejecución (desde la raíz de adn-monitor, con entorno):

```bash
export ADN_CONFIG_PATH=/opt/adn-monitor/monitor/adn-mon.yaml
python proxy/proxy.py
# o
python proxy/proxy.py --config /ruta/a/adn-mon.yaml
```

Usar **systemd** u otro supervisor junto a **`monitor.py`** y la pila **PHP**.

---

## RPTO, opciones y self-service

El proxy **nunca** envía **RPTO** directamente al hotspot para actualizaciones self-service. Envía **RPTO al MASTER** (peer server); el servidor actualiza bridges/opciones y aplica el flujo HBP normal.

| Evento | Comportamiento del proxy |
|--------|---------------------------|
| ~**10 s** tras login del hotspot (**RPTC**) | Leer **`Clients.options`** de la BD → **RPTO** → master `(MASTER, dport)`. |
| Cada ~**10 s** | Filas con **`modified = 1`** → **RPTO** → master, luego limpiar **`modified`**. |
| El hotspot envía **RPTO** | Reenvío al master; actualizaciones de BD según implementación. |

Detalle: [Self-service](self-service.md) y **`proxy/README.md`** en adn-monitor.

---

## Visibilidad en el monitor

Los hotspots aparecen en el panel solo si el **peer server** envía **informes TCP** al mismo host/puerto que **`ADN_CONNECTION`** en **`adn-mon.yaml`**. Alinea **`REPORTS`** en el servidor con **`ADN_IP` / `ADN_PORT`**. Ver [Monitor e informes](../server/user-guide/monitoring.md).

---

## Ver también

- [Configuración del monitor](configuration.md) — referencia **`adn-mon.yaml`** (resumen PROXY).
- [Arquitectura](architecture.md) — dónde encaja el proxy en la pila.
- [Self-service](self-service.md) — BD, **`modified`**, temporización RPTO.
