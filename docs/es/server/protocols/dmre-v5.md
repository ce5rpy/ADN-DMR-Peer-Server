# Disposición de trama DMRE v5

Esta página describe el formato en cable **OpenBridge DMRE** cuando el **byte de versión de protocolo embebido** es **5** (a menudo llamado **«OpenBridge v5»** en documentación de operadores — igual que **DMRE v5**; ver [OpenBridge](openbridge.md#dmre-and-openbridge-v5)).

Los datagramas **OpenBridge** extendidos usan el opcode **`DMRE`** (bytes `D`,`M`,`R`,`E`) y un campo **versión**. Cuando el byte de versión embebido es **> 4**, el paquete tiene **89 bytes** con **saltos** en el byte **72** y **BLAKE2b** de **73** a **89**.

## Forma corta (85 bytes)

Cuando la versión embebida es **≤ 4**, se omite **repetidor fuente**; **saltos** y **MAC** se desplazan (ver implementación en `udp_hbp.py`).

## Resumen de campos (v5 de 89 bytes)

| Región | Contenido |
|--------|-----------|
| 0:4 | Opcode `DMRE` |
| 4:5 | Secuencia |
| 5:8 | Fuente RF |
| 8:11 | ID destino |
| 11:15 | ID servidor |
| 15:16 | Bits (slot, tipo llamada, tipo trama, dtype/vseq) |
| 16:20 | Stream ID |
| 20:53 | Carga de voz |
| 53:55 | BER, RSSI |
| 55:56 | Versión de protocolo embebida |
| 56:64 | Marca de tiempo (ns, big-endian) |
| 64:68 | ID servidor de origen |
| 68:72 | Repetidor fuente (extendido v5) |
| 72:73 | Saltos |
| 73:89 | MAC BLAKE2b (16 bytes) |

**Integridad:** BLAKE2b-128 con la **passphrase** como clave; la MAC cubre los bytes **antes** del campo MAC.

La disposición de bytes en código (`infrastructure/twisted_adapters/udp_hbp.py`) es autoritativa y puede recibir aclaraciones menores con el tiempo.
