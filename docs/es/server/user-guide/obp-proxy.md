# Proxy OBP (puerto de entrada único)

La stanza opcional `OBP_PROXY` configura el listener fan-in para todos los sistemas `MODE: OPENBRIDGE`. Con el proxy activo, las instancias OpenBridge son **inject-only** (sin `listenUDP` por bridge en `HBPProtocol`); el proxy gestiona todo el UDP OBP entrante.

## Activación

| YAML | Comportamiento |
|------|----------------|
| Sin `OBP_PROXY`, sin OPENBRIDGE | N/A (no se arranca proxy). |
| Sin `OBP_PROXY`, con OPENBRIDGE | **Proxy por defecto** (`LISTEN_PORT` 62032, `BIND_LEGACY_PORTS` true). |
| `OBP_PROXY.ENABLED: false` | Modo legacy: cada OPENBRIDGE hace bind en su `PORT`. |
| `OBP_PROXY.ENABLED: true` | El proxy gestiona toda la entrada OBP (igual que bloque ausente). |

## Configuración

```yaml
OBP_PROXY:
  ENABLED: true
  LISTEN_PORT: 62032      # puerto estándar OBP fan-in (pareja de PROXY 62031)
  LISTEN_IP: ""           # dirección de bind opcional
  BIND_LEGACY_PORTS: true # default: también escucha cada SYSTEMS.*.PORT
  DEBUG: false
```

Las secciones OPENBRIDGE no cambian (`PORT`, `NETWORK_ID`, `PASSPHRASE`, `TARGET_*`, ACL, etc.). Con proxy activo, `PORT` se conserva como metadato (`_REPORT_PORT` internamente) para monitor/report y listeners legacy opcionales.

## Migración por bridge (`BIND_LEGACY_PORTS: true`)

Con el flag global activo, cada OPENBRIDGE migra de forma individual:

| `SYSTEMS.*.PORT` | Comportamiento |
|------------------|----------------|
| Igual a `OBP_PROXY.LISTEN_PORT` (p. ej. 62032) | Solo fan-in para ese bridge (sin listener legacy extra). |
| Omitido, `0` o vacío | Igual que `LISTEN_PORT` — solo fan-in (bridge migrado). |
| Otro puerto (p. ej. 62999) | Se mantiene el listener legacy de ese bridge. |

Ejemplo: migrar `OBP-CL2` al fan-in compartido mientras `OBP-EU` conserva `PORT: 62999`.

## Migración

1. Configs existentes con OPENBRIDGE sin stanza `OBP_PROXY` ya usan defaults (`BIND_LEGACY_PORTS: true`) — sin cambios en remotos.
2. Opcionalmente añadir bloque `OBP_PROXY` explícito para ajustar `LISTEN_PORT` / `BIND_LEGACY_PORTS`.
3. `BIND_LEGACY_PORTS: false` y cerrar puertos legacy cuando todos usen `LISTEN_PORT`.

- `NETWORK_ID` único entre OPENBRIDGE habilitados.
- `LISTEN_PORT` sin colisión con ningún `PORT` de sección si `BIND_LEGACY_PORTS` es true.
- `RELAX_CHECKS: true` recomendado para aprender `TARGET_SOCK` del primer paquete válido.

Ver también: [protocolo OpenBridge](../protocols/openbridge.md).
