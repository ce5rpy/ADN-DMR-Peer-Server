# Rendimiento (2.x)

**adn-server 2.x** y **adn-monitor 2.x** incluyen varios cambios que reducen trabajo de CPU y huella de memoria frente a **adn-dmr-server** y al stack antiguo de monitor/proxy. Esta página resume **qué** mejora y **qué lo provoca**.

## Resumen

| Área | Efecto típico | Causa principal |
|------|---------------|-----------------|
| **Downlink de voz (proxy inject)** | Menos CPU con tráfico de grupo intenso | **`PeerDownlinkIndex`** — fan-out solo a peers que encajan `(slot, TG)` en lugar de escanear todos los hotspots por paquete |
| **Origen ACTIVE en bridge** | Lookup más rápido | **Índices del `SubscriptionStore`** (`relay_tables_with_active_source`) — O(1) por `(system, slot, tgid)` frente a recorrer filas |
| **CPU de fondo** | Menos despertares | **OPTIONS / TG estática por eventos** — eliminado el bucle legacy cada **26 s** `options_config_loop` ([Comportamiento y temporizadores](behaviour-and-timers.md)) |
| **Ráfaga de logins** | Menos CONFIG redundante | **`ConfigPushThrottle`** — debounce adaptativo al empujar CONFIG al monitor |
| **Informes vs voz** | La voz se bloquea menos por informes | **`BoundedReportQueue`** — snapshots coalescidos, drenado acotado por tick |
| **Cable servidor → monitor** | Menos serializar/enviar | **Informe v2** JSON (`routing_table`, `topology`, `voice_event`) en lugar de pickle periódico de `CONFIG`/`BRIDGES` ([Protocolo de informes v2](../protocols/report-v2.md)) |
| **Procesos (RAM)** | Un proceso Python en lugar de dos | **`PROXY` integrado** en `adn-server.py` — sin proceso **adn-proxy** aparte ([Proxy hotspot](../user-guide/hotspot-proxy.md)) |
| **RAM / WS del monitor** | Estado de panel más compacto | **Wire slim `dashboard_state`**, `clean_sys_dict`, fingerprints WS más ligeros ([Arquitectura del monitor](../../monitor/architecture.md)) |

## Servidor: índice de downlink inject-only

La mayor ganancia de **CPU** en muchas redes ADN está en el camino **MASTER inject-only** (`PROXY` en modo inject-only).

**Legacy:** `send_peers` recorre **todos los peers registrados** por cada paquete de downlink → coste **O(peers × paquetes/s)**.

**2.x:** `PeerDownlinkIndex` precalcula candidatos desde **OPTIONS** (TG estáticas) y estado **UA** de cada peer. Por cada frame de voz de grupo solo se consideran peers que **podrían** querer ese `(slot, TG)`; cada candidato sigue pasando `peer_should_receive_group_voice`.

```text
Legacy:  cada DMRD  →  probar los N peers
2.x:     cada DMRD  →  lookup en índice  →  probar k peers  (k ≪ N en proxies cargados)
```

El parse de OPTIONS se **guarda en caché por peer** (`_CACHED_OPTIONS_STATIC`): si el blob OPTIONS no cambió, se reutilizan las TG estáticas ya parseadas en lugar de volver a interpretarlo en cada paquete.

| Código | Rol |
|--------|-----|
| `application/routing/peer_downlink_index.py` | Construcción del índice y `(slot, tgid) → candidatos` |
| `infrastructure/twisted_adapters/udp_hbp.py` | `_iter_downlink_peers`, `send_peers` |
| `tests/infrastructure/test_peer_downlink_fanout.py` | Tests de fan-out inject-only |

**Cuándo se nota:** proxy con **decenas o cientos** de hotspots y voz de grupo continua. En una conferencia pequeña con pocos peers, la diferencia es pequeña.

## Servidor: índices de enrutado

En cada frame de voz de grupo el servidor debe encontrar tablas donde **este system es origen ACTIVE**.

**Legacy:** recorrer filas dentro de `BRIDGES[clave]`.

**2.x:** `InMemorySubscriptionStore.relay_tables_with_active_source()` usa el índice **`_source_tables`** — lookup por `(system, slot, dst_tgid)` sin recorrer todas las patas.

Está en la implementación del store; es un **índice algorítmico**, no una opción de configuración aparte.

| Código | Rol |
|--------|-----|
| `infrastructure/subscription_store.py` | `_source_tables`, `_by_table`, `_active_target_counts` |
| `application/subscription/router.py` | `SubscriptionRouter.resolve()` |

## Servidor: menos trabajo periódico y en tormenta de logins

| Cambio | Qué evita |
|--------|-----------|
| **Sin bucle OPTIONS 26 s** | Timer cada 26 s en todos los systems cuando RPTO/arranque/reload ya refrescan bridges estáticos |
| **`ConfigPushThrottle`** | Inundar al monitor con snapshots CONFIG cuando muchos peers conectan en pocos segundos (debounce ~0,3 s → ~2 s en ráfaga) |
| **`BoundedReportQueue`** | Encode pickle/JSON y envío TCP en el hot path de voz; coalesce de snapshots config/bridge duplicados |

## Servidor: informes y despliegue

- **Informe v2** — JSON estructurado sustituye snapshots pickle opacos de bridge/config en el cable hacia **monitor 2.x**. Ver [Monitor e informes](../user-guide/monitoring.md) y [Protocolo de informes v2](../protocols/report-v2.md).
- **Proxy integrado** — `PROXY` **in-process**; quitar **adn-proxy** standalone ahorra **RAM** base (un intérprete, config compartida) y simplifica operación.

## Monitor (adn-monitor 2.x)

Empareja **adn-server 2.x** con **adn-monitor 2.x** para las mejoras del lado informes:

| Cambio | Efecto |
|--------|--------|
| **Wire slim / `dashboard_state`** | El monitor ingiere JSON compacto en lugar de duplicar árboles pickle v1 |
| **`clean_sys_dict`** | Expulsión periódica de entradas obsoletas en memoria (tope de crecimiento en paneles largos) |
| **Caché lastheard, fingerprints WS ligeros** | Menos trabajo por refresco del dashboard |
| **Stack FastAPI unificado** | Eliminados API PHP y proceso **proxy** standalone del monitor |

Detalle: [Arquitectura del monitor](../../monitor/architecture.md).

## Cuándo se nota la diferencia

| Despliegue | CPU | RAM |
|------------|-----|-----|
| Pocos masters, sin proxy inject, tráfico bajo | Poca | Poca |
| **Proxy inject-only, muchos hotspots, TG activa** | **Clara** (índice downlink) | Moderada (un proceso servidor vs servidor+proxy) |
| Monitor largo + informe v2 | Moderada (menos serializar en cable) | **Más clara** en monitor (estado slim, `clean_sys_dict`) |

Crypto, AMBE y MAC OpenBridge siguen dominando en tramos OBP cargados — optimizar la tabla de bridge no elimina ese coste.

## Lecturas relacionadas

- [Arquitectura](architecture.md) — capas y entrypoint
- [BRIDGES vs Subscriptions](bridges-vs-subscriptions.md) — modelo de enrutado (no es feature de rendimiento)
- [Comportamiento y temporizadores](behaviour-and-timers.md) — OPTIONS por eventos vs bucle 26 s legacy
- [Proxy hotspot](../user-guide/hotspot-proxy.md) — `PROXY` integrado / inject-only
- [Protocolo de informes v2](../protocols/report-v2.md) — cable JSON al monitor
- Notas de versión: `CHANGELOG.md` en la raíz del repositorio (`Performance` en **2.0.0-rc.1**).
