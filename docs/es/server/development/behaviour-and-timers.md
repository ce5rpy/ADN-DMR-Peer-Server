# Comportamiento y temporizadores

## Bucles de control estables

El servidor usa tareas **Twisted** `LoopingCall` para trabajo periódico: reglas de bridge, poda de flujos, refresco de opciones OpenBridge, recarga de alias, recarga de config de voz, descargas de seguridad, informes y pings de mantenimiento.

Los intervalos forman parte del **comportamiento observable** del producto (operadores e integradores pueden apoyarse en la temporización para diagnóstico). Evita **refrescos extra** o trabajo duplicado en **rutas calientes** (p. ej. manejadores por paquete para OpenBridge) cuando la misma preocupación ya la cubre el bucle programado — mantiene la carga predecible y evita aplicar reglas dos veces.

## Visibilidad de la configuración

El estado en tiempo de ejecución vive en un **`config` dict** compartido: opciones de peers, `SUB_MAP`, campos de plano de control OpenBridge (`_bcsq`, `_bcka`), y similares. Los adaptadores actualizan esta estructura; los casos de uso la leen. Así coincide con cómo se inspecciona el proceso en ejecución en logs y escenarios de soporte.
