# Echo (reproducción)

## Qué es

**Echo** graba voz de **grupo** entrante y la reproduce en el TG **9990**. Corre como **PEER** conectado al master **ECHO** del peer server principal (bridge TG 9990).

El runtime de playback forma parte de **`adn-server`**; ejecútalo con **`adn-server.py --echo`** y un **`adn-echo.yaml`** mínimo.

## Configuración

Usa un **YAML aparte y mínimo** — solo lo que el PEER necesita para unirse a **ECHO** en `adn-server.yaml`:

| Campo | Rol |
|-------|------|
| `GLOBAL.SERVER_ID` | Identidad de red del echo (suele ser `9990`) |
| `LOGGER` | Archivo de log (opcional pero recomendado) |
| `SYSTEMS.ECHO` | `MODE: PEER`, `IP`/`PORT` local, `MASTER_IP`/`MASTER_PORT`, `PASSPHRASE`, `RADIO_ID`, `CALLSIGN`, `OPTIONS` |

No hace falta `PROXY`, `ALIASES` ni `REPORTS`. **`MASTER_PORT`** y **`PASSPHRASE`** deben coincidir con **`ECHO`** en el servidor principal.

- Copia **`adn-echo.example.yaml`** → **`adn-echo.yaml`** (no se commitea).
- Ejecuta:

```bash
python adn-server.py --echo -c adn-echo.yaml
```

En producción suele ir en una unidad **systemd** aparte (ver `examples/systemd/adn-echo.service` en el repo), mismo binario:

```bash
sudo cp examples/systemd/adn-echo.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now adn-echo
```

## Relación con TG 9990

El servidor principal expone un master **ECHO** en **TG 9990** para el bridge de eco. El servicio **echo** independiente es un proceso aparte con su propia config que se conecta a ese master.

## Documentación

Esta página es el resumen incluido en el repositorio; amplía las notas de despliegue localmente según necesites.
