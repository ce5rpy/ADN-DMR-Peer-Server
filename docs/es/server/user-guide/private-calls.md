# Llamadas privadas

## Descripción general

Las llamadas **unitarias (privadas)** usan un camino distinto a la voz de **grupo**. El router usa **`SUB_MAP`** (suscriptor → último sistema/slot/tiempo conocido) y reglas de colisión para decidir si y dónde reenviar.

## SUB_MAP

- Se rellena cuando las estaciones registran tráfico; persiste vía ruta pickle **`SUB_MAP`** configurada bajo **`ALIASES`**.
- Sirve para resolver **ID de radio de destino** a un **sistema destino** y **slot** para el reenvío privado.

## OpenBridge frente a MASTER

El manejo privado usa ramas CSBK/datos/unit, búsqueda `SUB_MAP` y comprobaciones de slot ocupado donde aplique (ver `BridgeUseCases` en el código).

## TG / ID 4000 (unitaria)

Como en [Números especiales](special-numbers.md), una llamada **privada** a **4000** desactiva dinámicos y **no** se trata como ruta privada normal.

## Informes

Los eventos privados **START/END** pueden emitirse al cliente TCP de informes si **`REPORTS.REPORT`** está habilitado, análogo a voz de grupo (forma `PRIVATE VOICE,...` donde esté implementado).

Para detalles de ingreso de protocolo, ver [HBP](../protocols/hbp.md) y los casos de uso de bridge en código (`BridgeUseCases._pvt_call_received`).
