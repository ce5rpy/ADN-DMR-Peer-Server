# Behaviour and timers

## Stable control loops

The server uses **Twisted** `LoopingCall` tasks for periodic work: bridge rules, stream trimming, OpenBridge options refresh, alias reload, voice config reload, security downloads, reporting, and maintenance pings.

Intervals are part of the **observable behaviour** of the product (operators and integrators may rely on timing for troubleshooting). Avoid adding **extra** refreshes or duplicate work inside **hot paths** (for example per-packet handlers for OpenBridge) when the same concern is already covered by the scheduled loop—this keeps load predictable and avoids double application of rules.

## Configuration visibility

Runtime state lives in a shared **`config`** dict: options from peers, `SUB_MAP`, OpenBridge control-plane fields (`_bcsq`, `_bcka`), and similar. Adapters update this structure; use cases read it. This matches how the running process is inspected in logs and support scenarios.
