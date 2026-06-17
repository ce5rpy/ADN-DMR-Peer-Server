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

## Dynamic TG persistence (MariaDB) {#dynamic-tg-persistence-mariadb}

Since **2.0.0-rc.3**, user-activated dynamic TGs for each hotspot can be **persisted in MariaDB** (`peer_dynamic_tgs`) so they survive **hotspot disconnect/reconnect** without re-keying the TG.

| Event | Server behaviour |
|-------|------------------|
| **Group voice header** (new dynamic TG on a slot) | Registers UA session in memory and **async upsert** to `peer_dynamic_tgs`. |
| **RPTC** (hotspot login OK) | **Restores** rows for that peer/system into memory and re-syncs bridge rows (`ensure_dynamic_relay`). |
| **TG 4000** | Clears **all** dynamic slots for that peer (memory + DB). See [Special numbers — TG 4000](special-numbers.md#tg--id-4000--deactivate-dynamic-bridges). |
| **Hotspot disconnect** | Clears per-peer **mirror** state only; persisted rows and global `_PEER_UA_*` maps are kept until expiry or TG 4000. |
| **Periodic purge** | Every **60 s**, expired **SINGLE=1** rows are removed from DB and memory. |

**SINGLE=0** peers accumulate several dynamic TGs per slot in memory (`_PEER_UA_MULTI_TGS`). **SINGLE=1** stores one exclusive TG per slot with a timer.

**TG 4000** is never stored as a dynamic session (reset command only).

Requires **`DATABASE`** in `adn-server.yaml` — see [Configuration](configuration.md#database-mariadb).

## Cross-slot static TG downlink (inject-only)

On **inject-only** MASTER systems (integrated **`PROXY`**), group voice downlink respects **static TGs listed in either TS1 or TS2 OPTIONS**, even when the **wire timeslot** differs. This matches legacy REPEAT behaviour for hotspots that list a TG on one slot but transmit on another.

The server does **not** rewrite the incoming DMRD slot; it filters **which peers receive** the repeated packet via `peer_should_receive_group_voice` and the downlink index.

## Source-row guard and safe iteration

Forwarding is allowed only when the current system has a matching **ACTIVE source row** for that TG/slot context. This prevents accidental forwarding from rows that are present but not currently eligible as source legs.

`BRIDGES` scans and updates are also protected against concurrent row mutations during runtime loops, so timer/debug passes do not corrupt active iteration state.

## OpenBridge and TG display

For OpenBridge, the **DMR destination** in the packet may differ from the **TGID** in a bridge row (remap). Monitoring may show **RX TG** (as received) vs **TX TG** (as rewritten for a destination); correlate by **`stream_id`**, not TG alone.

## Contention

Group voice uses **hang time**, **`STREAM_TO`**, and slot `TX_*` / `RX_*` state to avoid colliding transmissions on the same resources.

See also: [Special numbers](special-numbers.md), [OpenBridge protocol](../protocols/openbridge.md).
