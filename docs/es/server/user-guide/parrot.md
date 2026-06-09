# Parrot (reproducción)

## Qué es

**Parrot** graba voz de **grupo** entrante y la reproduce (eco / parrot). Corre como **PEER** conectado al master **ECHO** del peer server principal (bridge TG 9990).

El runtime de playback forma parte de **`adn-server`**; ejecuta **`adn-server.py --parrot`** con un **`adn-parrot.yaml`** mínimo.

## Configuración

Usa un **YAML aparte y mínimo** — solo lo que el PEER necesita para unirse a **ECHO** en `adn-server.yaml`:

| Campo | Rol |
|-------|-----|
| `GLOBAL.SERVER_ID` | Identidad de red del parrot (suele ser `9990`) |
| `LOGGER` | Fichero de log (opcional pero recomendado) |
| `SYSTEMS.PARROT` | `MODE: PEER`, `IP`/`PORT` local, `MASTER_IP`/`MASTER_PORT`, `PASSPHRASE`, `RADIO_ID`, `CALLSIGN`, `OPTIONS` |

No hace falta `PROXY`, `ALIASES` ni `REPORTS`. **`MASTER_PORT`** y **`PASSPHRASE`** deben coincidir con **`ECHO`** en el servidor principal.

- Copiar **`adn-parrot.example.yaml`** → **`adn-parrot.yaml`** (no versionada).
- Ejecutar:

```bash
python adn-server.py --parrot -c adn-parrot.yaml
```

En producción: unidad **systemd** aparte (plantilla `examples/systemd/adn-parrot.service`):

```bash
sudo cp examples/systemd/adn-parrot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adn-parrot
```

## Relación con TG 9990 / ECHO

El servidor principal puede exponer un bridge **ECHO** en **TG 9990** para eco en banda. **Parrot** es un **servicio independiente** con su propia config — usa uno u otro según el despliegue.

## Documentación

Esta página es el resumen incluido en el repositorio; amplía las notas de despliegue localmente si hace falta.
