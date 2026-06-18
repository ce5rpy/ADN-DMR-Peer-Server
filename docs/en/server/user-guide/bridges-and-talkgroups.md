# Bridges and talkgroups

## `BRIDGES` model

The bridge table maps **talkgroup keys** (strings, e.g. `"26811"`, `"#reflector"`) to **rows**. Each row describes:

- **`SYSTEM`** — which configured system originates or receives this leg.
- **`TS`** — timeslot (1 or 2). OpenBridge sources are normalised to **TS1** in routing (`bridge_match_slot`).
- **`TGID`** — destination ID bytes for LC rewrite toward that leg.
- **`ACTIVE`** — whether this leg participates.
- **`TIMEOUT`**, **`TO_TYPE`**, **`ON`/`OFF`/`RESET`** — activation semantics (user-activated bridges, reflectors, etc.).

The router scans `BRIDGES` for an **ACTIVE** row matching the **current source system**, **slot**, and **destination TG** before forwarding (`dmrd_received` → `to_target`).

In **adn-server 2.x** the same rules live in **`SubscriptionStore`** / **`SubscriptionRouter`**; `BRIDGES` is only an export shape for the monitor. See [BRIDGES vs Subscriptions](../development/bridges-vs-subscriptions.md).

## Dynamic vs static

- **User-activated** bridges are created when a user keys a TG without a pre-built row (subject to `DEFAULT_UA_TIMER` and options).
- **Static** TGs and **STAT** bridges are created from **OPTIONS** / `make_static_tg` / `GEN_STAT_BRIDGES` flows.

## Source-row guard and safe iteration

Forwarding is allowed only when the current system has a matching **ACTIVE source row** for that TG/slot context. This prevents accidental forwarding from rows that are present but not currently eligible as source legs.

`BRIDGES` scans and updates are also protected against concurrent row mutations during runtime loops, so timer/debug passes do not corrupt active iteration state.

## OpenBridge and TG display

For OpenBridge, the **DMR destination** in the packet may differ from the **TGID** in a bridge row (remap). Monitoring may show **RX TG** (as received) vs **TX TG** (as rewritten for a destination); correlate by **`stream_id`**, not TG alone.

## Contention

Group voice uses **hang time**, **`STREAM_TO`**, and slot `TX_*` / `RX_*` state to avoid colliding transmissions on the same resources.

See also: [Special numbers](special-numbers.md), [OpenBridge protocol](../protocols/openbridge.md).
