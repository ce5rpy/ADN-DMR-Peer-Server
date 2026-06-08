# Protocolo de informes v2 (JSON)

**Estado:** borrador de esquema (V2-P1-001). La **codificación en wire** y la emisión en el servidor son **V2-P1-002**; el consumidor en monitor es **V2-P1-005**.

## Objetivos

Sustituir instantáneas al monitor que hoy usan **pickle** (`CONFIG_SND`, `BRIDGE_SND`) y **CSV** (`BRDG_EVENT`) por **JSON tipado**. El modo legacy sigue con `REPORTS.PROTOCOL: legacy` (shim, V2-P1-003).

## Transporte (sin cambios)

- TCP **netstring** (Twisted `NetstringReceiver`), mismo puerto que v1 (`REPORTS.REPORT_PORT`).
- Cada trama: **1 byte de opcode** + payload **JSON UTF-8** (v2) o pickle/CSV (v1).

### Opcodes

| Opcode | Hex | Payload v1 | Payload v2 |
|--------|-----|------------|------------|
| `HELLO` | `0xFF` | JSON hello (`protocol`: 1) | JSON hello (`report_protocol`: 2) |
| `CONFIG_SND` | `0x01` | pickle SYSTEMS | — (`TOPOLOGY_SND`) |
| `BRIDGE_SND` | `0x03` | pickle BRIDGES | — (`ROUTING_TABLE_SND`) |
| `BRDG_EVENT` | `0x07` | texto CSV | — (`VOICE_EVENT_SND`) |
| `TOPOLOGY_SND` | `0x10` | — | JSON `topology` |
| `ROUTING_TABLE_SND` | `0x11` | — | JSON `routing_table` |
| `VOICE_EVENT_SND` | `0x12` | — | JSON `voice_event` |
| `DELTA_SND` | `0x13` | — | JSON `delta` |

Los opcodes `0x10`–`0x13` están reservados en esta fase; pueden ajustarse antes de P1-002.

## Handshake (`hello`)

Al conectar, el servidor envía **`HELLO` (`0xFF`)** primero. Clientes v2 miran `report_protocol`:

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

| Campo | Notas |
|-------|--------|
| `report_protocol` | **2** para este esquema. Distinto del campo legacy `protocol: 1`. |
| `features` | Tokens v1 sin cambios; v2 añade `REPORT_V2` y capacidades de payload. |

## Tipos de mensaje

| `type` | Sustituye | Uso |
|--------|-----------|-----|
| `topology` | `CONFIG_SND` | Sistemas, peers, piernas OBP (sin secretos). |
| `routing_table` | `BRIDGE_SND` | Piernas de bridge por TG / reflector. |
| `voice_event` | `BRDG_EVENT` | Inicio/fin/ingress de llamadas. |
| `delta` | — | Parche incremental desde `since_seq`. |

## Payloads de referencia

Cada trama lleva un único objeto JSON con `type` obligatorio. Los ejemplos usan IDs anonimizados.

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

| Campo | Tipo | Obligatorio | Notas |
|-------|------|-------------|-------|
| `seq`, `ts` | int, float | sí | Secuencia monótona y epoch. |
| `systems[].name` | string | sí | Clave de sistema (config). |
| `systems[].mode` | string | sí | `MASTER`, `PEER` u `OPENBRIDGE`. |
| `systems[].enabled` | bool | sí | Flag enabled de config. |
| `systems[].ip`, `port` | string, int | no | Endpoint de escucha/conexión. |
| `systems[].repeat` | bool | no | Repeat en master. |
| `systems[].enhanced_obp` | bool | no | OBP enhanced. |
| `systems[].peers[]` | array | no | `{id, connected, ip?, port?}` por radio peer. |

Sin contraseñas ni material de cifrado (a diferencia del pickle legacy).

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

| Campo | Tipo | Obligatorio | Notas |
|-------|------|-------------|-------|
| `routes[].bridge_key` | string | sí | TG o clave reflector (`#nnn`). |
| `legs[].system` | string | sí | Nombre del sistema destino. |
| `legs[].ts` | 1 \| 2 | sí | Timeslot (legacy `TS`). |
| `legs[].tgid` | int | sí | Talkgroup (1–16777215). |
| `legs[].active` | bool | sí | Pierna activa en BRIDGES. |
| `legs[].to_type` | string | sí | `ON`, `OFF`, `STAT` o `NONE`. |
| `legs[].timer_expires_at` | float | no | Expiración `rule_timer` (legacy `TIMER`). |

### `voice_event`

CSV legacy:

```text
GROUP VOICE,START,RX,MASTER-A,2155905152,1001,3120001,2,52090
```

Equivalente v2:

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

| Campo | Tipo | Obligatorio | Valores / notas |
|-------|------|-------------|-----------------|
| `call_family` | string | sí | `GROUP`, `PRIVATE`, `UNIT`, `VCSSBK`. |
| `phase` | string | sí | `INGRESS`, `START`, `END`. |
| `direction` | string | sí | `RX`, `TX`. |
| `stream_id` | int | sí | Stream HBP 32 bits. |
| `peer_id`, `src_id`, `dst_id` | int | sí | IDs DMR (1–16777215). |
| `slot` | int | sí | `1` o `2`. |
| `duration_s` | float \| null | no | En eventos `END`. |

Semántica OpenBridge INGRESS/START: ver [Monitor e informes](../user-guide/monitoring.md).

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

| Campo | Tipo | Obligatorio | Notas |
|-------|------|-------------|-------|
| `since_seq` | int | sí | Último `seq` aplicado por el cliente. |
| `patch` | object | sí | Parcial `topology` o `routing_table` (misma forma). |

## Secuenciación

- `topology` y `routing_table` llevan `seq` (uint) y `ts` (epoch float).
- `delta` indica `since_seq` respecto al último `seq` aplicado por el cliente.

## Configuración (prevista)

```yaml
REPORTS:
  REPORT: true
  REPORT_PORT: 4321
  PROTOCOL: legacy   # legacy | v2
```

## Compatibilidad

| Servidor | Monitor | Modo |
|----------|---------|------|
| 1.0.x | 1.0.x | legacy + HELLO v1 |
| 2.0.0-alpha | 1.0.x | shim legacy |
| 2.0.0-alpha | 2.x | report v2 opt-in |

Ver también [Monitor e informes](../user-guide/monitoring.md).
