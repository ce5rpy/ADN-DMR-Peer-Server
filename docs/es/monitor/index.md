# ADN Monitor (descripción general)

**ADN Monitor** es un proyecto distinto del **ADN DMR Peer Server**, pero ambos suelen desplegarse **juntos**: el servidor envía **informes TCP** (o MQTT) al monitor; el monitor alimenta el **panel web** (React) y las actualizaciones **WebSocket**. Un único proceso **`monitor.py`** (FastAPI) sirve **REST** (`/api/*`), **WebSocket** (`/ws`) e **ingest** de informes. Opcional: **MySQL** (self-service / Last Heard) y **proxy hotspot** integrado en **`adn-server.py`**.

Este capítulo documenta la pila **adn-monitor** con el mismo nivel de detalle que las guías del servidor. El código fuente está en el repositorio **adn-monitor**, no en el repositorio **adn-server** (donde se mantiene esta documentación).

## Qué hace cada parte

| Parte | Rol |
|-------|-----|
| **`monitor/monitor.py`** | FastAPI: REST (`/api/*`), WebSocket (`/ws`), ingest TCP o MQTT, estado **CTABLE** / Last Heard, self-service MySQL. |
| **`frontend/`** | React (Vite): UI del panel; mismo origen `/api` + `/ws`. |

## Ficheros de configuración

| Fichero | Quién lo usa | Variable típica |
|---------|----------------|-----------------|
| **`adn-server.yaml`** | **`adn-server.py`** (**`PROXY`** / **`SELF_SERVICE`** integrados) | `-c` / ruta por defecto junto al binario |
| **`monitor/adn-monitor.yaml`** | **`monitor.py`** | **`ADN_CONFIG_PATH`** |

**`SELF_SERVICE`** (MySQL / PBKDF2) debe **coincidir** entre **`adn-server.yaml`** y **`adn-monitor.yaml`**. **`ADN_CONNECTION`**, panel, WebSocket y alias van en **`adn-monitor.yaml`**; **`PROXY`** integrado va en **`adn-server.yaml`** — ver [Proxy hotspot integrado](../server/user-guide/hotspot-proxy.md).

## Enlace con el peer server

| Servidor (`adn-server.yaml`) | Monitor (`adn-monitor.yaml`) |
|------------------------------|---------------------------|
| **`REPORTS.REPORT_CLIENTS`** — lista de IPs permitidas para conectar **al** listener de informes, o el host del monitor | **`ADN_CONNECTION.ADN_IP`** / **`ADN_PORT`** — a dónde **se conecta** el monitor (debe coincidir con el bind y puerto de informes del servidor). |
| **`REPORTS.REPORT_PORT`** — puerto TCP en el que el **servidor escucha** conexiones de informes | El mismo puerto que **`ADN_PORT`**. |

Ver [Monitor e informes](../server/user-guide/monitoring.md) para los opcodes de informes y [Configuración del monitor](configuration.md) para cada sección de `adn-monitor.yaml`.

## Ver también

- [Proxy hotspot (integrado)](../server/user-guide/hotspot-proxy.md) — `PROXY` en `adn-server.yaml`
- [Arquitectura e implantación](architecture.md)
- [Configuración (`adn-monitor.yaml`)](configuration.md)
- [Self-service](self-service.md)
