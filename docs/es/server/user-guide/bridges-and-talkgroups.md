# Bridges y talkgroups

## Modelo `BRIDGES`

La tabla de bridges asocia **claves de talkgroup** (cadenas, p. ej. `"26811"`, `"#reflector"`) con **filas**. Cada fila describe:

- **`SYSTEM`** — qué sistema configurado origina o recibe esta pata.
- **`TS`** — slot temporal (1 o 2). Las fuentes OpenBridge se normalizan a **TS1** en el enrutado (`bridge_match_slot`).
- **`TGID`** — bytes de ID de destino para reescritura LC hacia esa pata.
- **`ACTIVE`** — si esta pata participa.
- **`TIMEOUT`**, **`TO_TYPE`**, **`ON`/`OFF`/`RESET`** — semántica de activación (bridges activados por usuario, reflectores, etc.).

El router recorre `BRIDGES` buscando una fila **ACTIVE** que coincida con el **sistema de origen actual**, **slot** y **TG de destino** antes de reenviar (`dmrd_received` → `to_target`).

## Dinámico frente a estático

- Los bridges **activados por usuario** se crean cuando alguien pulsa una TG sin fila previa (sujeto a `DEFAULT_UA_TIMER` y opciones).
- Las TG **estáticas** y bridges **STAT** se crean desde flujos **OPTIONS** / `make_static_tg` / `GEN_STAT_BRIDGES`.

## Persistencia TG dinámicos (MariaDB) {#persistencia-tg-dinamicos-mariadb}

Desde **2.0.0-rc.3**, los TG dinámicos activados por usuario de cada hotspot pueden **persistirse en MariaDB** (`peer_dynamic_tgs`) para sobrevivir a **desconexión/reconexión** sin volver a pulsar el TG.

| Evento | Comportamiento del servidor |
|--------|----------------------------|
| **Cabecera de voz de grupo** (nuevo TG dinámico en un slot) | Registra sesión UA en memoria y **upsert asíncrono** en `peer_dynamic_tgs`. |
| **RPTC** (login OK del hotspot) | **Restaura** filas de ese peer/system en memoria y re-sincroniza bridges (`ensure_dynamic_relay`). |
| **TG 4000** | Borra **todos** los slots dinámicos de ese peer (memoria + BD). Ver [Números especiales — TG 4000](special-numbers.md#tg--id-4000--desactivar-bridges-dinamicos). |
| **Desconexión del hotspot** | Solo limpia el **espejo** por peer; las filas persistidas y mapas globales `_PEER_UA_*` se mantienen hasta expiración o TG 4000. |
| **Purga periódica** | Cada **60 s**, filas **SINGLE=1** expiradas se eliminan de BD y memoria. |

Peers **SINGLE=0** acumulan varios TG dinámicos por slot (`_PEER_UA_MULTI_TGS`). **SINGLE=1** guarda un TG exclusivo por slot con temporizador.

**TG 4000** nunca se almacena como sesión dinámica (solo comando de reset).

Requiere **`DATABASE`** en `adn-server.yaml` — ver [Configuración](configuration.md#database-mariadb).

## Downlink cross-slot de TG estáticas (inject-only)

En MASTER **inject-only** ( **`PROXY`** integrado), el downlink de voz de grupo respeta **TG estáticas listadas en OPTIONS de TS1 o TS2**, aunque el **slot en cable** sea otro. Equivale al comportamiento legacy REPEAT para hotspots que listan un TG en un slot y transmiten en otro.

El servidor **no** reescribe el slot del DMRD entrante; filtra **a qué peers reenvía** el paquete repetido con `peer_should_receive_group_voice` y el índice de downlink.

## Guardia de fila de origen e iteración segura

El reenvío solo se permite cuando el sistema actual tiene una **fila de origen ACTIVE** que coincide con ese contexto TG/slot. Esto evita reenviar desde filas presentes pero no elegibles como patas de origen.

Los recorridos y actualizaciones de `BRIDGES` también están protegidos frente a mutaciones concurrentes de filas durante bucles en ejecución, de forma que los pases de temporizador/debug no corrompan el estado de iteración activa.

## OpenBridge y visualización de TG

En OpenBridge, el **destino DMR** en el paquete puede diferir del **TGID** en una fila de bridge (remap). El monitor puede mostrar **TG RX** (recibida) frente a **TG TX** (reescrita para un destino); correlaciona por **`stream_id`**, no solo por TG.

## Contención

La voz de grupo usa **hang time**, **`STREAM_TO`** y estado de slot `TX_*` / `RX_*` para evitar transmisiones simultáneas en los mismos recursos.

Ver también: [Números especiales](special-numbers.md), [Protocolo OpenBridge](../protocols/openbridge.md).
