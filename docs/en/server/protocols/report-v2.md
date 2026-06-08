# Report protocol v2 (JSON)

**Status:** schema draft (V2-P1-001). **Wire encoding** and server emission are **V2-P1-002**; monitor consumer is **V2-P1-005**.

## Goals

Replace monitor snapshots that today use **pickle** (`CONFIG_SND`, `BRIDGE_SND`) and **CSV strings** (`BRDG_EVENT`) with **typed JSON** that any client can decode.

**Release policy:** **adn-server 1.0.x** + **adn-monitor 1.0.x** = report v1 (frozen tag pair). **2.x** server emits **report v2 only** (no pickle shim, no `dual`); **adn-monitor 2.x** is required on the same release line.

## Transport (unchanged)

- TCP **netstring** frames (Twisted `NetstringReceiver`), same port as v1 (`REPORTS.REPORT_PORT`).
- Each frame: **1-byte opcode** + **UTF-8 JSON payload** (v2) or pickle/CSV (v1).

### Opcodes

| Opcode | Hex | v1 payload | v2 payload |
|--------|-----|------------|------------|
| `HELLO` | `0xFF` | JSON hello (`protocol`: 1) | JSON hello (`report_protocol`: 2) |
| `CONFIG_SND` | `0x01` | pickle SYSTEMS | — (use `TOPOLOGY_SND`) |
| `BRIDGE_SND` | `0x03` | pickle BRIDGES | — (use `ROUTING_TABLE_SND`) |
| `BRDG_EVENT` | `0x07` | CSV text | — (use `VOICE_EVENT_SND`) |
| `TOPOLOGY_SND` | `0x10` | — | JSON `topology` |
| `ROUTING_TABLE_SND` | `0x11` | — | JSON `routing_table` |
| `VOICE_EVENT_SND` | `0x12` | — | JSON `voice_event` |
| `DELTA_SND` | `0x13` | — | JSON `delta` |

Proposed opcodes `0x10`–`0x13` are reserved in the schema phase; exact values may change before P1-002 ships.

## Handshake (`hello`)

On connect the server sends **`HELLO` (`0xFF`)** first (same as today). v2 clients inspect `report_protocol`:

```json
{
  "type": "hello",
  "server": "adn-server",
  "version": "2.0.0-alpha.1",
  "report_protocol": 2,
  "features": ["INGRESS", "END_TX_FORWARD", "PUSH_ON_CONNECT", "REPORT_V2", "TOPOLOGY_JSON", "ROUTING_TABLE_JSON", "VOICE_EVENT_JSON", "DELTA_UPDATES"],
  "systems": ["MASTER-A", "OBP-CL"]
}
```

| Field | Notes |
|-------|--------|
| `report_protocol` | **2** for this schema. Distinct from legacy field `protocol: 1`. |
| `features` | v1 tokens unchanged; v2 adds `REPORT_V2` and payload capabilities. |

Monitor **1.0.x** does not speak this wire; use the **1.0.x** server tag for that pair.

## Message types

| `type` | Replaces | Purpose |
|--------|----------|---------|
| `topology` | `CONFIG_SND` | Systems, peers, OpenBridge legs (no secrets). |
| `routing_table` | `BRIDGE_SND` | Active bridge legs per talkgroup / reflector key. |
| `voice_event` | `BRDG_EVENT` | Structured call start/end/ingress. |
| `delta` | — | Incremental `topology` or `routing_table` patch since `since_seq`. |

## Reference payloads

Each frame payload is one JSON object with a required `type`. Examples below use anonymized IDs.

### `topology`

```json
{
  "type": "topology",
  "seq": 1,
  "ts": 1717555200.0,
  "systems": [
    {
      "name": "MASTER-A",
      "mode": "MASTER",
      "enabled": true,
      "ip": "10.0.0.1",
      "port": 62030,
      "repeat": true,
      "peers": [
        { "id": 3120001, "connected": true, "ip": "10.0.0.50", "port": 62031 }
      ]
    },
    {
      "name": "OBP-CL",
      "mode": "OPENBRIDGE",
      "enabled": true,
      "ip": "10.0.0.2",
      "port": 62044,
      "enhanced_obp": true,
      "peers": []
    }
  ]
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `seq`, `ts` | int, float | yes | Monotonic sequence and epoch time. |
| `systems[].name` | string | yes | System key (matches config). |
| `systems[].mode` | string | yes | `MASTER`, `PEER`, or `OPENBRIDGE`. |
| `systems[].enabled` | bool | yes | Config enabled flag. |
| `systems[].ip`, `port` | string, int | no | Listen/connect endpoint. |
| `systems[].repeat` | bool | no | Master repeat flag. |
| `systems[].enhanced_obp` | bool | no | OpenBridge enhanced mode. |
| `systems[].peers[]` | array | no | `{id, connected, ip?, port?}` per peer radio. |

No passwords or encryption material are included (unlike legacy pickle).

### `routing_table`

```json
{
  "type": "routing_table",
  "seq": 42,
  "ts": 1717555260.5,
  "routes": [
    {
      "bridge_key": "52090",
      "legs": [
        {
          "system": "MASTER-A",
          "ts": 2,
          "tgid": 52090,
          "active": true,
          "to_type": "ON",
          "timer_expires_at": 1717555320.0
        },
        {
          "system": "MASTER-B",
          "ts": 2,
          "tgid": 52090,
          "active": true,
          "to_type": "ON"
        }
      ]
    },
    {
      "bridge_key": "#310",
      "legs": [
        {
          "system": "MASTER-A",
          "ts": 2,
          "tgid": 310,
          "active": false,
          "to_type": "NONE"
        }
      ]
    }
  ]
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `routes[].bridge_key` | string | yes | Talkgroup id or reflector key (`#nnn`). |
| `legs[].system` | string | yes | Target system name. |
| `legs[].ts` | 1 \| 2 | yes | Timeslot (legacy `TS`). |
| `legs[].tgid` | int | yes | Talkgroup (1–16777215). |
| `legs[].active` | bool | yes | Leg active in BRIDGES table. |
| `legs[].to_type` | string | yes | `ON`, `OFF`, `STAT`, or `NONE`. |
| `legs[].timer_expires_at` | float | no | `rule_timer` expiry (legacy `TIMER`). |

### `voice_event`

Legacy CSV:

```text
GROUP VOICE,START,RX,MASTER-A,2155905152,1001,3120001,2,52090
```

v2 equivalent:

```json
{
  "type": "voice_event",
  "ts": 1717555201.234,
  "call_family": "GROUP",
  "phase": "START",
  "direction": "RX",
  "system": "MASTER-A",
  "stream_id": 2155905152,
  "peer_id": 1001,
  "src_id": 3120001,
  "slot": 2,
  "dst_id": 52090,
  "duration_s": null
}
```

| Field | Type | Required | Values / notes |
|-------|------|----------|----------------|
| `call_family` | string | yes | `GROUP`, `PRIVATE`, `UNIT`, `VCSSBK`. |
| `phase` | string | yes | `INGRESS`, `START`, `END`. |
| `direction` | string | yes | `RX`, `TX`. |
| `stream_id` | int | yes | 32-bit HBP stream id. |
| `peer_id`, `src_id`, `dst_id` | int | yes | DMR ids (1–16777215). |
| `slot` | int | yes | `1` or `2`. |
| `duration_s` | float \| null | no | Set on `END`. |

OpenBridge **INGRESS** vs **START** semantics match [Monitoring and reports](../user-guide/monitoring.md#openbridge-monitor-semantics): use `phase: "INGRESS"` for first sight, `phase: "START"` after loop control.

### `delta`

```json
{
  "type": "delta",
  "seq": 43,
  "ts": 1717555261.0,
  "since_seq": 42,
  "patch": {
    "type": "routing_table",
    "seq": 43,
    "ts": 1717555261.0,
    "routes": [
      {
        "bridge_key": "52090",
        "legs": [
          {
            "system": "MASTER-A",
            "ts": 2,
            "tgid": 52090,
            "active": false,
            "to_type": "ON"
          }
        ]
      }
    ]
  }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `since_seq` | int | yes | Last `seq` the client applied. |
| `patch` | object | yes | Partial `topology` or `routing_table` (same shape). |

## Sequencing

- `topology` and `routing_table` messages carry monotonic `seq` (uint) and `ts` (float epoch).
- Clients track last applied `seq`; `delta` messages set `since_seq` to the client watermark.
- Full snapshots may still be sent on connect and on `REPORTS.REPORT_INTERVAL` (same triggers as v1 CONFIG/BRIDGE).

## Configuration

```yaml
REPORTS:
  REPORT: true
  REPORT_PORT: 4321
```

No `PROTOCOL` switch on **2.x** — wire is always JSON (`infrastructure/twisted_adapters/report/wire.py`). Payload mapping: **`application/report/`**.

**`rule_timer`**, **`stat_trimmer`**, and **`bridgeDebug`** use **routing deltas** when only part of `BRIDGES` changed; connect, `REPORT_INTERVAL`, reload, and client `CONFIG_REQ` / `BRIDGE_REQ` send **full** snapshots.

## Version pairing (supported combinations)

| Server | Monitor | Report wire | Notes |
|--------|---------|-------------|--------|
| **1.0.x** | **1.0.x** | v1 (pickle/CSV) | Frozen pair; no cross-upgrade of report protocol |
| **2.0.0-alpha.\*** | **2.x** (dev) | v2 only | Current `develop` line |
| **2.0.0** | **2.0.x** | v2 only | GA pair; monitor 1.0.x **not** supported |

Do **not** run monitor 1.0.x against server 2.0.0 or monitor 2.x against server 1.0.x for production.

See also [Monitoring and reports](../user-guide/monitoring.md).
