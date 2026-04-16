# Behaviour and timers

## Stable control loops

The server uses **Twisted** `LoopingCall` tasks for periodic work: bridge rules, stream trimming, OpenBridge options refresh, alias reload, voice config reload, security downloads, reporting, and maintenance pings.

Intervals are part of the **observable behaviour** of the product (operators and integrators may rely on timing for troubleshooting). Avoid adding **extra** refreshes or duplicate work inside **hot paths** (for example per-packet handlers for OpenBridge) when the same concern is already covered by the scheduled loop—this keeps load predictable and avoids double application of rules.

## Configuration visibility

Runtime state lives in a shared **`config`** dict: options from peers, `SUB_MAP`, OpenBridge control-plane fields (`_bcsq`, `_bcka`), and similar. Adapters update this structure; use cases read it. This matches how the running process is inspected in logs and support scenarios.

## Core timer intervals (operational contract)

The following intervals are part of the current runtime behavior:

| Loop | Interval | Role |
|------|----------|------|
| `rule_timer` | **52s** | Bridge timeout/on-off state progression. |
| `stream_trimmer` | **5s** | Stream cleanup, timeout handling, end-of-call state trimming. |
| `bridge_reset` | **6s** | Bridge reset flag cleanup and pending reset completion. |
| `options_config_loop` | **26s** | Refresh static TG / reflector options from peer OPTIONS payloads. |
| `statTrimmer` | **303s** | Trim stale STAT bridges and transient status entries. |

If you change one of these intervals, document the operational impact for monitoring, loop behavior, and troubleshooting.

## In-band VTERM scope

In-band bridge signalling on voice terminator (VTERM) is intentionally scoped to:

- call type **`group`**
- call type **`vcsbk`**

It is not applied on **unit/private** VTERM paths.

## Packet-control behavior notes

Current packet-control behavior for stream dedup and ordering:

- OBP hash duplicate-drop checks are evaluated with **`seq > 0`** guard.
- HBP still computes/stores CRC for `seq == 0`, while duplicate-drop by CRC remains guarded by **`seq > 0`**.
- This avoids over-dropping first-packet edge cases while preserving stream duplicate protection.
