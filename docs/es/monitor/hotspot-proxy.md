# Proxy hotspot

## Proxy integrado (predeterminado actual)

**ADN DMR Peer Server** incluye un **proxy hotspot integrado** en **`adn-server.py`**. Configura **`PROXY`** y **`SELF_SERVICE`** en **`adn-server.yaml`** — ver [Proxy hotspot (integrado)](../server/user-guide/hotspot-proxy.md).

- Los hotspots se conectan solo a **`PROXY.LISTEN_PORT`** (fan-in).
- El tráfico se inyecta en **`PROXY.TARGET_SYSTEM`** (MASTER solo inyección, **`MAX_PEERS`**).
- El self-service MySQL usa la misma tabla **`Clients`** que este stack del monitor.
- **Desactiva** **`adn-proxy`** independiente en el mismo host para evitar conflictos en **`LISTEN_PORT`**.

---

## Proxy independiente (legado, repo adn-monitor)

El repositorio **adn-monitor** sigue teniendo un **relé UDP independiente** (`proxy/proxy.py`). Asigna a cada hotspot un **puerto de destino dedicado** en el host del peer server (rango de puertos + **`GENERATOR`**). Usa este layout solo si mantienes el proxy separado de **`adn-server`** a propósito.

Estructura: `proxy/proxy.py`, paquete `proxy/src/adn_proxy/` (arquitectura limpia). **GPL v3** (derivado del proxy original de Simon Adlem, G7RZU).

### Por qué también va con el monitor {#why-it-ships-with-the-monitor-not-inside-the-peer-server}

- **Mismo despliegue** que el panel: **`adn-monitor.yaml`**, **`adn-proxy.yaml`**, **PHP**, **MySQL**.
- Separación histórica: peer server = núcleo radio; proxy = frontal UDP opcional en un **rango** de puertos.
- Los despliegues ADN nuevos deben preferir el proxy **integrado** salvo que mantengas una unidad **`adn-proxy`** existente.

---

## Fichero de configuración {#configuration-file}

El proxy **independiente** **no** usa `adn-server.yaml` para su propio proceso. Lee un YAML que incluye **`PROXY`**, **`SELF_SERVICE`** y **`LOGGER`** (log del proxy). El proxy **integrado** lee esos bloques desde **`adn-server.yaml`**.

### Orden de resolución

| Prioridad | Origen | Uso |
|-----------|--------|-----|
| 1 | **`python proxy/proxy.py --config /ruta/fichero.yaml`** | Sobrescribe la ruta solo para este proceso. |
| 2 | **`ADN_PROXY_CONFIG_PATH`** | Variable opcional: ruta absoluta a **`adn-proxy.yaml`** (config dedicada del proxy). |
| 3 | **`ADN_CONFIG_PATH`** | Legado: ruta a un **fichero combinado** (p. ej. **`adn-monitor.yaml`** con **PROXY** incrustado — igual que monitor/backend). |
| 4 | **Por defecto** | **`proxy/adn-proxy.yaml`** junto a `proxy/proxy.py` si no hay variables de entorno. |

Copia **`proxy/adn-proxy.example.yaml`** a **`proxy/adn-proxy.yaml`** y edita. **`SELF_SERVICE`** debe coincidir con **`monitor/adn-monitor.yaml`** (mismas credenciales MySQL y PBKDF2).

Secciones leídas del fichero elegido:

- **`PROXY`** — dirección de escucha, host master, **rango** de puertos de destino, timeouts, debug, listas negras.
- **`SELF_SERVICE`** — MySQL y **`USE_SELFSERVICE`** (tabla **`Clients`**, RPTO / opciones).
- **`LOGGER`** — **`LOG_PATH`** y **`PROXY_LOG_FILE`** (separado del **`LOG_FILE`** de `adn-monitor.yaml` para `monitor.py`).

**Entorno** opcional (ver `proxy/README.md` en el repo): p. ej. **`ADN_PROXY_DEBUG`**, **`ADN_PROXY_LISTENPORT`**.

---

## Claves `PROXY` (en `adn-proxy.yaml`, o YAML combinado legado)

| Clave | Rol |
|-------|-----|
| **MASTER** | IP o **nombre de host** del **ADN DMR Peer Server**. Se resuelve a IPv4 al arrancar (Twisted necesita IP para `write()`). |
| **LISTEN_PORT** | Puerto UDP donde los **hotspots** se conectan **al proxy** (lo que configuran en el hotspot). |
| **LISTEN_IP** | Vacío suele significar todas las interfaces; si no, enlazar a esa dirección. |
| **PORT** / **DESTPORT_START** | Puerto UDP base en **`MASTER`** (alias **DESTPORT_START**); debe coincidir con **`SYSTEM.PORT`** en `adn-server`. |
| **GENERATOR** | El mismo entero que **`SYSTEM.GENERATOR`**; puertos UDP **`PORT`…`PORT+GENERATOR-1`** en **`MASTER`** (uno por sesión de hotspot proxy). |
| **TIMEOUT** | Tiempo de inactividad / sesión (segundos). |
| **STATS** | Registro extra de estadísticas. |
| **DEBUG** | Log detallado de paquetes (o **`ADN_PROXY_DEBUG=1`**). |
| **CLIENT_INFO** | Información por cliente en logs. |
| **BLACK_LIST** / **IP_BLACK_LIST** | Bloquear IDs de radio o IPs de origen. |

Las claves internas tras la carga usan nombres mixtos (`Master`, `ListenPort`, …) — ver `adn_proxy.infrastructure.config_loader`.

---

## El peer server (`adn-server.yaml`) debe cubrir el rango de puertos

El proxy reenvía tráfico a **`MASTER:puerto_asignado`** por cliente; **puerto_asignado** se elige en **`PORT`…`PORT+GENERATOR-1`** (la misma semántica de **PORT**/**GENERATOR** que en [Configuración del servidor](../server/user-guide/configuration.md)).

El **ADN DMR Peer Server** debe **escuchar UDP** en **ese host** en **cada puerto** de ese rango (normalmente mediante **`GENERATOR`** en un bloque SYSTEM).

- Alinea **`PROXY.PORT`** y **`PROXY.GENERATOR`** con **`SYSTEM.PORT`** y **`SYSTEM.GENERATOR`** en **`adn-server.yaml`**.
- Configuración típica: un **`MODE: MASTER`** con **`GENERATOR`** que expande a `SYSTEM-0`…`SYSTEM-(N-1)` en puertos UDP consecutivos — ver [Configuración del servidor](../server/user-guide/configuration.md).

Si el servidor solo escucha p. ej. en **56400** pero el proxy envía a **56401**, ese cliente no se registrará.

---

## Cómo arranca el proceso

1. Resolver ruta de config (`--config`, **`ADN_PROXY_CONFIG_PATH`**, **`ADN_CONFIG_PATH`**, o por defecto **`proxy/adn-proxy.yaml`**).
2. **`load_config()`** parsea YAML → **`PROXY`**, **`SELF_SERVICE`**, **`LOG`**.
3. Pool **MySQL** opcional si self-service / funciones de BD están activas.
4. El **reactor** Twisted ejecuta UDP **ProxyProtocol** en **`LISTEN_IP:LISTEN_PORT`**, reenviando a **`MASTER:puerto_destino_asignado`**.

Ejecución (desde la raíz de adn-monitor):

```bash
# YAML dedicado del proxy (recomendado)
export ADN_PROXY_CONFIG_PATH=/opt/adn-monitor/proxy/adn-proxy.yaml
python proxy/proxy.py

# O usar por defecto proxy/adn-proxy.yaml tras copiar desde adn-proxy.example.yaml
python proxy/proxy.py

# Legado: un solo YAML combinado con el monitor
export ADN_CONFIG_PATH=/opt/adn-monitor/monitor/adn-monitor.yaml
python proxy/proxy.py

# O ruta explícita para una ejecución
python proxy/proxy.py --config /opt/adn-monitor/proxy/adn-proxy.yaml
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

Los hotspots aparecen en el panel solo si el **peer server** envía **informes TCP** al mismo host/puerto que **`ADN_CONNECTION`** en **`adn-monitor.yaml`**. Alinea **`REPORTS`** en el servidor con **`ADN_IP` / `ADN_PORT`**. Ver [Monitor e informes](../server/user-guide/monitoring.md).

---

## Ver también

- [Configuración del monitor](configuration.md) — **`adn-monitor.yaml`** (panel, informes, MySQL para backend/monitor); detalle **`PROXY`** arriba.
- [Arquitectura](architecture.md) — dónde encaja el proxy en la pila.
- [Self-service](self-service.md) — BD, **`modified`**, temporización RPTO.
