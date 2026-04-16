# HBP (HomeBrew Protocol) — DMRD

## Role

**HBP** is the UDP framing used between this server and **MASTER** / **PEER** systems. Payloads use the **`DMRD`** opcode (four ASCII bytes) followed by DMR voice/data fields (RF source, destination, stream ID, AMBE block, etc.).

## Authentication

- **MASTER** side: RPTL → salt → RPTK → config; peer options (**RPTO**) refresh bridge options.
- **PEER** side: connects upstream, repeats authentication, maintenance pings.

Implementation: `infrastructure/twisted_adapters/udp_hbp.py` (`HBPProtocol`).

## OpenBridge vs HBP

OpenBridge uses **`DMRD`** v1 (HMAC-SHA1) or **`DMRE`** (extended); see [OpenBridge](openbridge.md). HBP **MASTER/PEER** links use classic **DMRD** rules.

## BER / RSSI

For non-OpenBridge sources, optional **BER/RSSI** bytes may be appended after the 53-byte voice payload in ingress; forwarding to OpenBridge may strip or preserve fields depending on destination and `to_target` rules.
