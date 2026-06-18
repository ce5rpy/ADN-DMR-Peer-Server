# Proxy de informes (paneles legacy)

**ADN DMR Peer Server 2.x** emite **informe wire v2** (JSON por TCP). **adn-monitor 2.x** entiende ese protocolo y se conecta **directamente** al servidor — no hace falta ningún componente extra.

Algunos **stacks de panel legacy** siguen trayendo su propio backend `dashboard.py` / `monitor.py` y solo hablan **informe wire v1** (pickle `CONFIG_SND` / `BRIDGE_SND`, CSV `BRDG_EVENT`). Esos monitores **no pueden** conectarse a **adn-server 2.x** en el puerto de informes.

El paquete opcional **[ADN-report-proxy](https://github.com/ce5rpy/ADN-report-proxy)** queda en medio: se conecta **upstream** al servidor real (v2), escucha **downstream** donde el monitor legacy espera el servidor (v1) y traduce **v2 → v1**.

| Stack | Servidor upstream | ¿Funciona sin proxy? |
|-------|-------------------|----------------------|
| **adn-monitor 2.x** (React) | **adn-server 2.x** | Sí — conectar a `REPORTS.REPORT_PORT` |
| Panel legacy + monitor incluido (v1) | **adn-dmr-server** (v1) | Sí — directo al puerto de informes del servidor |
| Panel legacy + monitor incluido (v1) | **adn-server 2.x** (v2) | **No** — usar **report-proxy** |

Objetivos legacy típicos: forks antiguos de **ADN-Dashboard**, despliegues **HBMonitor** / **FDMR Monitor** que aún ejecutan un proceso monitor Python contra `dashboard.cfg` / `monitor.cfg`.

## Topología

```text
┌───────────────────┐
│    adn-server     │
│   ESCUCHA :4321   │
└─────────▲─────────┘
          │
          │  TCP v2 JSON
          │  (report-proxy es CLIENTE)
          │
┌─────────┴─────────┐
│   report-proxy    │
│   ESCUCHA :4322   │
└─────────▲─────────┘
          │
          │  TCP v1 pickle
          │  (panel legacy es CLIENTE)
          │
┌─────────┴─────────┐
│   panel legacy    │
│    monitor.py     │
└───────────────────┘
```

| Componente | Rol | Puerto por defecto | Config | Clave |
|------------|-----|-------------------|--------|-------|
| **adn-server** | Escucha clientes de informes | **4321** | `adn-server.yaml` | `REPORTS.REPORT_PORT` |
| **report-proxy** | Se conecta al servidor | 4321 | `report-proxy.yaml` | `UPSTREAM.PORT` |
| **report-proxy** | Escucha al monitor legacy | **4322** | `report-proxy.yaml` | `LISTEN.PORT` |
| **Panel legacy** | Se conecta al proxy | **4322** | `dashboard.cfg` | `SERVER_PORT` |

**No** apuntes el panel legacy al **4321** — es el puerto v2 del servidor.

**No** pongas `UPSTREAM.PORT` en **4322** — es el puerto de escucha del propio proxy.

## Lado servidor (`adn-server.yaml`)

Los informes deben estar activos y la **IP del host del proxy** debe estar en la lista permitida:

```yaml
REPORTS:
  REPORT: true
  REPORT_INTERVAL: 60
  REPORT_PORT: 4321
  REPORT_CLIENTS: "127.0.0.1"   # IP de la máquina donde corre report-proxy
```

Si el proxy corre en otro host, usa la **IP de ese host** en `REPORT_CLIENTS`, no solo `127.0.0.1`. Ver [Configuración](configuration.md#reports) para todas las claves de `REPORTS`.

## Proxy y panel legacy

Instala y ejecuta el proxy desde el repositorio **[ADN-report-proxy](https://github.com/ce5rpy/ADN-report-proxy)** (`report-proxy.yaml`, `python3 report-proxy.py -c report-proxy.yaml`). Apunta `UPSTREAM` al `REPORT_PORT` del servidor y `LISTEN` al puerto que usa el monitor legacy (a menudo **4322**).

En `dashboard.cfg` / `monitor.cfg` legacy:

```ini
[SERVER CONNECTION]
SERVER_IP = 127.0.0.1
SERVER_PORT = 4322
```

`SERVER_IP` es el host donde **report-proxy** escucha, no necesariamente el host de adn-server.

**Orden de arranque:** adn-server → report-proxy → backend monitor legacy.

Pasos completos, ejemplos multi-host, comprobaciones y errores frecuentes: **[README de ADN-report-proxy](https://github.com/ce5rpy/ADN-report-proxy#configuration-legacy-dashboard--adn-server-2x)**.

## Traducción de wire (resumen)

| Upstream (v2 desde adn-server) | Downstream (v1 al monitor legacy) |
|--------------------------------|-----------------------------------|
| `HELLO` (`report_protocol: 2`) | `HELLO` (`protocol: 1`) |
| `STATE_SND` / `dashboard_state` | `CONFIG_SND` (pickle) |
| `ROUTING_TABLE_SND` | `BRIDGE_SND` (pickle) |
| `TOPOLOGY_SND` | `CONFIG_SND` (pickle) |
| `VOICE_EVENT_SND` | `BRDG_EVENT` (CSV) |

Detalle del esquema v2: [Protocolo de informes v2 (JSON)](../protocols/report-v2.md).

## Ver también

- [Monitor e informes](monitoring.md) — canal de informes, emparejamiento con **adn-monitor**, líneas de log.
- [Descripción general de ADN Monitor](../../monitor/index.md) — panel recomendado para **adn-server 2.x** (sin proxy).
