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

## Guardia de fila de origen e iteración segura

El reenvío solo se permite cuando el sistema actual tiene una **fila de origen ACTIVE** que coincide con ese contexto TG/slot. Esto evita reenviar desde filas presentes pero no elegibles como patas de origen.

Los recorridos y actualizaciones de `BRIDGES` también están protegidos frente a mutaciones concurrentes de filas durante bucles en ejecución, de forma que los pases de temporizador/debug no corrompan el estado de iteración activa.

## OpenBridge y visualización de TG

En OpenBridge, el **destino DMR** en el paquete puede diferir del **TGID** en una fila de bridge (remap). El monitor puede mostrar **TG RX** (recibida) frente a **TG TX** (reescrita para un destino); correlaciona por **`stream_id`**, no solo por TG.

## Contención

La voz de grupo usa **hang time**, **`STREAM_TO`** y estado de slot `TX_*` / `RX_*` para evitar transmisiones simultáneas en los mismos recursos.

Ver también: [Números especiales](special-numbers.md), [Protocolo OpenBridge](../protocols/openbridge.md).
