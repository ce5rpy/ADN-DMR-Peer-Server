# Proxy hotspot (integrado)

**ADN DMR Peer Server** incluye un **proxy hotspot integrado**: un solo proceso (`adn-server.py`) acepta Homebrew (HBP) de muchos hotspots en un único puerto UDP e **inyecta** el tráfico en un **MASTER** configurado. **No** hace falta un proceso **`adn-proxy`** aparte cuando este modo está activo.

La configuración está en **`adn-server.yaml`**, bloques **`PROXY`** y opcional **`SELF_SERVICE`** (misma tabla MySQL **`Clients`** que **adn-monitor**).

---

## Cuándo usarlo

| Despliegue | Qué ejecutar |
|------------|--------------|
| **Stack ADN habitual** (monitor + panel + muchos hotspots Pi-Star) | **`adn-server.py`** con **`PROXY`** + **`SELF_SERVICE`** — desactiva la unidad **`adn-proxy`** independiente para evitar conflicto en **`PROXY.LISTEN_PORT`**. |
| **Legado / config separada** | **`proxy/proxy.py`** en el repo **adn-monitor** — ver [Proxy hotspot (independiente)](../../monitor/hotspot-proxy.md). |

El proxy integrado usa **fan-in**: los hotspots solo necesitan **`PROXY.LISTEN_PORT`** (p. ej. **62031**). El **MASTER** destino es **solo inyección** — **no** abre su propio puerto UDP para ese system (sin rango de puertos por hotspot en el host del servidor).

---

## Dependencia opcional (self-service)

El self-service con MySQL requiere **`mysqlclient`**:

```bash
pip install -e ".[selfservice]"
```

Si **`USE_SELFSERVICE: true`** pero falta **`mysqlclient`**, el arranque falla con un error claro. Pon **`USE_SELFSERVICE: false`** para usar el proxy sin BD (sin actualizaciones **RPTO** desde el panel).

---

## Claves `PROXY`

| Clave | Rol |
|-------|-----|
| **LISTEN_PORT** | Puerto UDP al que se conectan los **hotspots** (el que configuran en el dispositivo). |
| **LISTEN_IP** | Dirección de bind; vacío = todas las interfaces. |
| **TARGET_SYSTEM** | Nombre del **MASTER** en **`SYSTEMS`** que recibe el HBP inyectado (debe existir y estar **ENABLED**). |
| **TIMEOUT** | Timeout de sesión inactiva (segundos); las sesiones caducadas se eliminan en el MASTER. |
| **DEBUG** | Log detallado de paquetes. |
| **CLIENT_INFO** | Log de conexión/desconexión por ID de radio. |
| **BLACK_LIST** | Bloquea IDs de radio listados. |
| **IP_BLACK_LIST** | Bloquea IPs origen (con caducidad opcional). |

En **`PROXY`** integrado **no** hay **`MASTER`**, **`PORT`** ni **`GENERATOR`** — eso corresponde al proxy independiente legado. El MASTER destino usa **`MAX_PEERS`** (no un rango UDP) para limitar hotspots simultáneos.

Ejemplo (de `adn-server.example.yaml`):

```yaml
PROXY:
  LISTEN_PORT: 62031
  LISTEN_IP: ""
  TARGET_SYSTEM: SYSTEM
  TIMEOUT: 30
  DEBUG: false
  CLIENT_INFO: true
  BLACK_LIST: []
  IP_BLACK_LIST: {}
```

### MASTER destino solo inyección

Cuando **`PROXY.TARGET_SYSTEM`** apunta a un system (p. ej. **`SYSTEM`**), al arrancar se **eliminan** **`IP`** / **`PORT`** de ese bloque MASTER. Los hotspots nunca se conectan al puerto de conferencia; todo el HBP entra por **`LISTEN_PORT`**.

Define **`MAX_PEERS`** en el MASTER destino como máximo de hotspots simultáneos (p. ej. **102**). Otros MASTER (**ECHO**, **D-APRS**, etc.) mantienen **`IP`** / **`PORT`** normales si no son el destino del proxy.

---

## Claves `SELF_SERVICE`

Misma semántica que **`adn-monitor.yaml`** / **`adn-proxy.yaml`** legado — tabla **`Clients`** compartida, flag **`modified`**, **RPTO** hacia el MASTER.

| Clave | Rol |
|-------|-----|
| **USE_SELFSERVICE** | Activa sincronización de opciones con MySQL (`true` / `false`). |
| **DB_SERVER**, **DB_USERNAME**, **DB_PASSWORD**, **DB_NAME**, **DB_PORT** | Conexión MySQL. |
| **PBKDF2_SALT**, **PBKDF2_ITERATIONS** | Deben **coincidir** con monitor/backend para el hash de contraseñas. |

Al arrancar el servidor registra **`(SELF_SERVICE) Database connection test: OK`** y **`(SELF_SERVICE) Enabled`** si el pool conecta. El self-service es **asíncrono**; el reenvío de voz no se bloquea por latencia de BD.

Detalle del flujo en el panel: [Self-service](../../monitor/self-service.md).

---

## Comportamiento con varios hotspots

- Cada hotspot autenticado es un **peer** en el MASTER de inyección con sus **OPTIONS** (TG estáticas). **Repeat** y el fan-out del monitor respetan **OPTIONS por peer** — el tráfico de un TG no se envía a peers que no lo tienen seleccionado.
- Los talkgroups **parrot / eco 9990–9999** omiten el filtro OPTIONS y vuelven al hotspot **llamante** (ver [Números especiales](special-numbers.md)).

---

## Recarga en caliente (`SIGHUP`)

**Se aplica sin reiniciar** (las sesiones activas del proxy se mantienen):

- **`PROXY`:** **TIMEOUT**, **DEBUG**, **CLIENT_INFO**, **BLACK_LIST**, **IP_BLACK_LIST**
- **`SELF_SERVICE`:** se fusiona en config (cambios de credenciales en nuevas operaciones BD; los bucles no se reinician en reload)

**Requiere reinicio completo del proceso:**

- **`PROXY.LISTEN_PORT`** / **`LISTEN_IP`** (el cambio de bind se registra y se ignora en reload)
- **`PROXY.TARGET_SYSTEM`**
- Activar o desactivar **`USE_SELFSERVICE`** tras el arranque

Ver [Configuración — recarga en caliente](configuration.md#recarga-en-caliente-adn-serveryaml).

---

## Proxy independiente (legado)

El repo **adn-monitor** sigue incluyendo **`proxy/proxy.py`** para despliegues con relay UDP **separado** y **`adn-proxy.yaml`**. **No** ejecutes el proxy integrado y **`adn-proxy`** independiente en el mismo **`LISTEN_PORT`**.

---

## Ver también

- [Configuración](configuration.md) — referencia completa de **`adn-server.yaml`**.
- [Monitorización e informes](monitoring.md) — informes TCP, panel, rotación de logs.
- [Self-service](../../monitor/self-service.md) — **`Clients`**, temporización **RPTO**.
- [Proxy hotspot (independiente)](../../monitor/hotspot-proxy.md) — layout legado **`adn-proxy`**.
