# Comportamiento y temporizadores

## Bucles de control estables

El servidor usa tareas **Twisted** `LoopingCall` para trabajo periódico: reglas de bridge, poda de flujos, refresco de opciones OpenBridge, recarga de alias, recarga de config de voz, descargas de seguridad, informes y pings de mantenimiento.

Los intervalos forman parte del **comportamiento observable** del producto (operadores e integradores pueden apoyarse en la temporización para diagnóstico). Evita **refrescos extra** o trabajo duplicado en **rutas calientes** (p. ej. manejadores por paquete para OpenBridge) cuando la misma preocupación ya la cubre el bucle programado — mantiene la carga predecible y evita aplicar reglas dos veces.

## Visibilidad de la configuración

El estado en tiempo de ejecución vive en un **`config` dict** compartido: opciones de peers, `SUB_MAP`, campos de plano de control OpenBridge (`_bcsq`, `_bcka`), y similares. Los adaptadores actualizan esta estructura; los casos de uso la leen. Así coincide con cómo se inspecciona el proceso en ejecución en logs y escenarios de soporte.

## Intervalos clave de temporizadores (contrato operativo)

Los siguientes intervalos forman parte del comportamiento actual en ejecución:

| Bucle | Intervalo | Rol |
|------|-----------|-----|
| `rule_timer` | **52s** | Progresión de timeout y estado on/off de bridges. |
| `stream_trimmer` | **5s** | Limpieza de streams, manejo de timeout y cierre de estado de llamada. |
| `bridge_reset` | **6s** | Limpieza de flags de reset y cierre de resets pendientes. |
| OPTIONS refresh | **por evento** | TG estáticas / reflector vía **RPTO**, **startup/reload** (`apply_startup_bridges`), fallback **dmrd** sin source. Sin loop periódico de 26s (**D-28**). |
| `dynamic_tg_purge_loop` | **60s** | Purga filas **SINGLE=1** expiradas de `peer_dynamic_tgs` y `_PEER_UA_SESSIONS` en memoria. |
| `statTrimmer` | **303s** | Limpieza de bridges STAT obsoletos y estados transitorios. |

Si cambias uno de estos intervalos, documenta el impacto operativo en monitorización, comportamiento de bucles y troubleshooting.

## Constantes de contención de voz

Estas constantes definen el comportamiento por paquete y por sesión. Están
documentadas en detalle en [Enrutado de voz y contención](routing-and-contention.md).

| Constante | Valor | Rol |
|---|---|---|
| `STREAM_TO` | **0.36 s** | Ventana para considerar un stream "activo" (entre paquetes). |
| `_STALE_PEER_SESSION_TIMEOUT` | **5.0 s** | Una sesión per-peer sin frames se considera muerta (VTERM perdido). |
| `GROUP_HANGTIME` | **5 s** (default config, por sistema) | Bloqueo tras fin de QSO antes de aceptar otro TG en ese slot. |
| `DEFAULT_UA_TIMER` | configurable (minutos, por sistema) | Duración de bridges dinámicos (User Activated). |

## Alcance de VTERM in-band

La señalización in-band en voice terminator (VTERM) está acotada a:

- tipo de llamada **`group`**
- tipo de llamada **`vcsbk`**

No se aplica en rutas VTERM **unit/private**.

## Notas de comportamiento de packet-control

Comportamiento actual para deduplicación y orden de streams:

- La deduplicación por hash en OBP se evalúa con guardia **`seq > 0`**.
- En HBP se calcula/guarda CRC también para `seq == 0`, pero la caída por duplicado por CRC sigue guardada por **`seq > 0`**.
- Esto evita sobre-descartar casos de primer paquete y mantiene protección de duplicados de stream.
