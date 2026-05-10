# ADN Monitor (descripción general)

**ADN Monitor** es un proyecto distinto del **ADN DMR Peer Server**, pero ambos suelen desplegarse **juntos**: el servidor envía **informes TCP** (config, bridges, eventos de llamada) al monitor; el monitor alimenta el **panel web** (React) y las actualizaciones **WebSocket**. Los componentes opcionales incluyen la **API PHP** (Slim), **MySQL** (self-service / registro de dispositivos) y el **proxy hotspot** (UDP entre hotspots y el peer server).

Este capítulo documenta la pila **adn-monitor** con el mismo nivel de detalle que las guías del servidor. El código fuente está en el repositorio **adn-monitor**, no en el repositorio **adn-server** (donde se mantiene esta documentación).

## Qué hace cada parte

| Parte | Rol |
|-------|-----|
| **`monitor/monitor.py`** | Python (Twisted): se conecta al **puerto TCP de informes** del peer server, decodifica cargas netstring (`CONFIG_SND`, `BRIDGE_SND`, `BRDG_EVENT`), mantiene **CTABLE** / **BTABLE**, escribe **Last Heard** / estadísticas de TG en **MySQL** si está configurado, sirve JSON **WebSocket** al panel. |
| **`backend/`** | PHP **Slim**: `/api/config/dashboard`, auth, APIs **self-service** opcionales, proxy de alias. Lee **`adn-monitor.yaml`** vía **`ADN_CONFIG_PATH`**. |
| **`frontend/`** | React (Vite): UI del panel; consume API del backend + WebSocket. |
| **`proxy/`** | Python (Twisted): **proxy hotspot** UDP; reenvía Homebrew entre hotspots y el peer server; lee **`Clients`** en MySQL para opciones **RPTO** (self-service). Carga **`adn-proxy.yaml`** por defecto (ver [Proxy hotspot](hotspot-proxy.md)). |

## Ficheros de configuración

| Fichero | Quién lo usa | Variable típica |
|---------|----------------|-----------------|
| **`monitor/adn-monitor.yaml`** | **`monitor.py`**, **backend PHP** | **`ADN_CONFIG_PATH`** |
| **`proxy/adn-proxy.yaml`** | **`proxy/proxy.py`** | **`ADN_PROXY_CONFIG_PATH`** (opcional; valores por defecto y legado en [Proxy hotspot](hotspot-proxy.md#configuration-file)) |

**`SELF_SERVICE`** (MySQL / PBKDF2) debe **coincidir** entre ambos YAML cuando separas la config. **`ADN_CONNECTION`**, panel, WebSocket y alias van en **`adn-monitor.yaml`**; los ajustes **`PROXY`** de escucha/master/rango van en **`adn-proxy.yaml`**, salvo que uses un **fichero único legado** vía **`ADN_CONFIG_PATH`** para el proxy.

## Enlace con el peer server

| Servidor (`adn-server.yaml`) | Monitor (`adn-monitor.yaml`) |
|------------------------------|---------------------------|
| **`REPORTS.REPORT_CLIENTS`** — lista de IPs permitidas para conectar **al** listener de informes, o el host del monitor | **`ADN_CONNECTION.ADN_IP`** / **`ADN_PORT`** — a dónde **se conecta** el monitor (debe coincidir con el bind y puerto de informes del servidor). |
| **`REPORTS.REPORT_PORT`** — puerto TCP en el que el **servidor escucha** conexiones de informes | El mismo puerto que **`ADN_PORT`**. |

Ver [Monitor e informes](../server/user-guide/monitoring.md) para los opcodes de informes y [Configuración del monitor](configuration.md) para cada sección de `adn-monitor.yaml`.

## Ver también

- [Proxy hotspot](hotspot-proxy.md) — `PROXY`, rango de puertos del peer, carga de config y arranque
- [Arquitectura e implantación](architecture.md)
- [Configuración (`adn-monitor.yaml`)](configuration.md)
- [Self-service](self-service.md)
