# Arquitectura e implantación

## Arquitectura limpia (monitor Python)

Bajo `monitor/src/adn_monitor/`:

- **Dominio** — objetos de valor, errores, tipos de opcode.
- **Aplicación** — `MonitorState`, `process_message` en `monitor_controller.py`, servicio de alias, casos de uso Last Heard / conteo TG, formato de hora.
- **Infraestructura** — `load_config` YAML, cliente Twisted **TCP** (`ReportClientFactory`) al peer server, fábrica **WebSocket** para el panel, repositorios MySQL, decodificadores pickle/json para `CONFIG_SND` / `BRIDGE_SND`.

El monitor **sale hacia** **`ADN_CONNECTION.ADN_IP:ADN_PORT`** y recibe mensajes con prefijo de longitud (estilo netstring). Actualiza **CTABLE** (masters/peers/OpenBridge) y **BTABLE** (bridges) en memoria, y persiste resultados de **BRDG_EVENT** cuando MySQL está configurado.

## Protocolo de informes (desde el peer server)

Los mismos opcodes que en la documentación del servidor: **CONFIG_SND**, **BRIDGE_SND**, **BRDG_EVENT**, etc. El monitor los decodifica y aplica en `process_message` — ver [Monitor e informes](../server/user-guide/monitoring.md).

## WebSocket

`monitor.py` ejecuta un **WebSocket** Twisted en **`WEBSOCKET_SERVER.WEBSOCKET_PORT`**, enviando instantáneas JSON a **`FREQUENCY`** para que la app React actualice sin polling del estado principal.

## Backend PHP

- **Slim 4** front controller: `backend/public/index.php`.
- Carga **`adn-monitor.yaml`** vía **`ADN_CONFIG_PATH`** (igual que el monitor).
- **`/api/config/dashboard`** — título, idioma, flags (`selfService`, `showConsole`, …) desde **`DASHBOARD`**.
- **`/api/auth/*`** — sesión por cookie cuando hay BD **SELF_SERVICE**.
- **`/api/self-service/*`** — opciones de dispositivo (ver [Self-service](self-service.md)).
- **`/api/aliases/*`** — proxy opcional a URLs de listas TG/bridge desde **ALIASES**.

## Frontend

- **Vite + React** bajo `frontend/`; el build genera estáticos servidos por nginx/Apache o similar.
- Usa **`API_BASE`** (build) para la API PHP y **URL del WebSocket** para datos en vivo.

## Proxy hotspot

**Integrado (predeterminado):** **`adn-server.py`** ejecuta fan-in UDP desde **`PROXY.LISTEN_PORT`** hacia **`PROXY.TARGET_SYSTEM`**; **`SELF_SERVICE`** en **`adn-server.yaml`** impulsa **RPTO** desde MySQL **`Clients`**. Ver [Proxy hotspot (integrado)](../server/user-guide/hotspot-proxy.md).

**Independiente (legado, repo adn-monitor):**

- Entrada: `proxy/proxy.py`; paquete `src/adn_proxy/` (dominio / aplicación / infraestructura).
- Lee **`PROXY`** y **`SELF_SERVICE`** desde **`adn-proxy.yaml`** por defecto (o YAML combinado del monitor vía **`ADN_CONFIG_PATH`** — ver [Proxy hotspot](hotspot-proxy.md#configuration-file)).
- Por cada cliente hotspot, asigna un puerto UDP en **`PORT`…`PORT+GENERATOR-1`** y reenvía a **`MASTER`**.
- Cuando **self-service** actualiza **`Clients.options`** y pone **`modified=1`**, el proxy envía **RPTO** al **master** en un temporizador (~10 s).

**Detalle:** [Proxy hotspot](hotspot-proxy.md) (integrado vs independiente, claves, arranque).

## Topología típica de despliegue

```text
[Hotspots] --UDP--> [Proxy :LISTEN_PORT] --UDP--> [Peer server :PORT..PORT+GENERATOR-1]
                           |
                           v
                    MySQL (Clients)

[Peer server :REPORT_PORT] <--- TCP --- [monitor.py : cliente que conecta]

[Navegador] --HTTPS--> [API PHP + frontend estático]
[Navegador] --WS----> [WebSocket del monitor :9000]
```

---

## Ver también

- [Inicio de la documentación](../README.md)
- [Configuración](configuration.md)
- [Self-service](self-service.md)
