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
| OPTIONS refresh | **event-driven** | Static TG / reflector from **RPTO**, **startup/reload** (`apply_startup_bridges`), **dmrd** no-source fallback. No periodic 26s loop (**D-28**). |
| `dynamic_tg_purge_loop` | **60s** | Purge expired **SINGLE=1** rows from `peer_dynamic_tgs` and in-memory `_PEER_UA_SESSIONS`. |
| `statTrimmer` | **303s** | Trim stale STAT bridges and transient status entries. |

If you change one of these intervals, document the operational impact for monitoring, loop behavior, and troubleshooting.

## Voice contention constants

These constants define per-packet and per-session behaviour. They are
documented in detail in [Voice routing and contention](routing-and-contention.md).

| Constant | Value | Role |
|---|---|---|
| `STREAM_TO` | **0.36 s** | Window to consider a stream "active" (between packets). |
| `_STALE_PEER_SESSION_TIMEOUT` | **5.0 s** | A per-peer session with no frames is considered dead (lost VTERM). |
| `GROUP_HANGTIME` | **5 s** (config default, per-system) | Blocking period after a QSO ends before another TG is accepted on that slot. |
| `DEFAULT_UA_TIMER` | configurable (minutes, per-system) | Duration of dynamic (User Activated) bridges. |

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
