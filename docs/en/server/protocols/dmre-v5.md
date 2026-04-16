# DMRE v5 frame layout

This page describes the **OpenBridge DMRE** wire format when the **embedded protocol version** is **5** (often called **“OpenBridge v5”** in operator docs — same as **DMRE v5**; see [OpenBridge](openbridge.md#dmre-and-openbridge-v5)).

Extended **OpenBridge** datagrams use the **`DMRE`** opcode (bytes `D`,`M`,`R`,`E`) and a **version** field. When the embedded version byte is **> 4**, the packet is **89 bytes** with **hops** at byte **72** and **BLAKE2b** from **73** to **89**.

## Short form (85 bytes)

When the embedded version is **≤ 4**, **source repeater** is omitted; **hops** and **MAC** shift (see implementation in `udp_hbp.py`).

## Field summary (89-byte v5)

| Region | Content |
|--------|---------|
| 0:4 | Opcode `DMRE` |
| 4:5 | Sequence |
| 5:8 | RF source |
| 8:11 | Destination ID |
| 11:15 | Server ID |
| 15:16 | Bits (slot, call type, frame type, dtype/vseq) |
| 16:20 | Stream ID |
| 20:53 | Voice payload |
| 53:55 | BER, RSSI |
| 55:56 | Embedded protocol version |
| 56:64 | Timestamp (ns, big-endian) |
| 64:68 | Source server ID |
| 68:72 | Source repeater (v5 extended) |
| 72:73 | Hops |
| 73:89 | BLAKE2b MAC (16 bytes) |

**Integrity:** BLAKE2b-128 with the **passphrase** as key; MAC covers bytes **before** the MAC field.

The byte layout in code (`infrastructure/twisted_adapters/udp_hbp.py`) is authoritative and may gain minor clarifications over time.
