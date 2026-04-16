# Bridges and talkgroups

## `BRIDGES` model

The bridge table maps **talkgroup keys** (strings, e.g. `"26811"`, `"#reflector"`) to **rows**. Each row describes:

- **`SYSTEM`** — which configured system originates or receives this leg.
- **`TS`** — timeslot (1 or 2). OpenBridge sources are normalised to **TS1** in routing (`bridge_match_slot`).
- **`TGID`** — destination ID bytes for LC rewrite toward that leg.
- **`ACTIVE`** — whether this leg participates.
- **`TIMEOUT`**, **`TO_TYPE`**, **`ON`/`OFF`/`RESET`** — activation semantics (user-activated bridges, reflectors, etc.).

The router scans `BRIDGES` for an **ACTIVE** row matching the **current source system**, **slot**, and **destination TG** before forwarding (`dmrd_received` → `to_target`).

## Dynamic vs static

- **User-activated** bridges are created when a user keys a TG without a pre-built row (subject to `DEFAULT_UA_TIMER` and options).
- **Static** TGs and **STAT** bridges are created from **OPTIONS** / `make_static_tg` / `GEN_STAT_BRIDGES` flows.

## OpenBridge and TG display

For OpenBridge, the **DMR destination** in the packet may differ from the **TGID** in a bridge row (remap). Monitoring may show **RX TG** (as received) vs **TX TG** (as rewritten for a destination); correlate by **`stream_id`**, not TG alone.

## Contention

Group voice uses **hang time**, **`STREAM_TO`**, and slot `TX_*` / `RX_*` state to avoid colliding transmissions on the same resources.

See also: [Special numbers](special-numbers.md), [OpenBridge protocol](../protocols/openbridge.md).
