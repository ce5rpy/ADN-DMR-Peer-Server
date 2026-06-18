# Performance (2.x)

**adn-server 2.x** and **adn-monitor 2.x** include several changes that reduce CPU work and memory footprint compared with **adn-dmr-server** and the old monitor/proxy stack. This page lists **what** improves and **what causes it**.

## At a glance

| Area | Typical effect | Main cause |
|------|----------------|------------|
| **Voice downlink (inject proxy)** | Lower CPU under busy group traffic | **`PeerDownlinkIndex`** — fan-out to peers that match `(slot, TG)` instead of scanning every connected hotspot per packet |
| **Bridge source lookup** | Faster “am I the ACTIVE source?” | **`SubscriptionStore`** indexes (`relay_tables_with_active_source`) — O(1) by `(system, slot, tgid)` vs scanning table rows |
| **Background CPU** | Fewer wakeups | **Event-driven OPTIONS / static TG** — removed legacy **26 s** `options_config_loop` ([Behaviour and timers](behaviour-and-timers.md)) |
| **Mass peer login** | Less redundant CONFIG traffic | **`ConfigPushThrottle`** — adaptive debounce on CONFIG push to the monitor |
| **Reporting vs voice** | Voice path less blocked by reports | **`BoundedReportQueue`** — coalesced snapshots, bounded drain per tick |
| **Server → monitor wire** | Less serialize/send work | **Report v2** JSON (`routing_table`, `topology`, `voice_event`) instead of periodic full pickle of `CONFIG`/`BRIDGES` ([Report protocol v2](../protocols/report-v2.md)) |
| **Process count (RAM)** | One Python process instead of two | **Integrated `PROXY`** in `adn-server.py` — no separate **adn-proxy** process ([Hotspot proxy](../user-guide/hotspot-proxy.md)) |
| **Monitor RAM / WS load** | Smaller in-memory dashboard state | **Slim `dashboard_state` wire**, `clean_sys_dict`, lighter WebSocket fingerprints ([Monitor architecture](../../monitor/architecture.md)) |

## Server: inject-only downlink index

The largest **CPU** win on many ADN networks is on the **MASTER inject-only** path (`PROXY` with inject-only mode).

**Legacy:** `send_peers` walks **every registered peer** for each downlink packet → cost grows as **O(peers × packets/s)**.

**2.x:** `PeerDownlinkIndex` precomputes candidates from each peer’s **OPTIONS** (static TGs) and **UA session** state. For each group voice frame, only peers that **might** want that `(slot, TG)` are considered; each candidate still passes `peer_should_receive_group_voice`.

```text
Legacy:  every DMRD  →  try all N peers
2.x:     every DMRD  →  index lookup  →  try k peers  (k ≪ N on busy proxies)
```

OPTIONS parsing is **cached per peer** (`_CACHED_OPTIONS_STATIC`): if the OPTIONS blob is unchanged, already-parsed static TGs are reused instead of re-parsing on every packet.

| Code | Role |
|------|------|
| `application/routing/peer_downlink_index.py` | Index build and `(slot, tgid) → candidates` |
| `infrastructure/twisted_adapters/udp_hbp.py` | `_iter_downlink_peers`, `send_peers` |
| `tests/infrastructure/test_peer_downlink_fanout.py` | Inject-only fan-out tests |

**When it matters:** proxy with **tens to hundreds** of hotspots and steady group voice. On a small conference with few peers, the difference is minor.

## Server: routing indexes

On every group voice frame the server must find relay tables where **this system is the ACTIVE source**.

**Legacy:** scan rows inside `BRIDGES[table_key]` (and related tables).

**2.x:** `InMemorySubscriptionStore.relay_tables_with_active_source()` uses a maintained **`_source_tables`** index — lookup by `(system, slot, dst_tgid)` without walking all legs.

This lives in the subscription store implementation; it is an **algorithmic index**, not a separate feature you configure.

| Code | Role |
|------|------|
| `infrastructure/subscription_store.py` | `_source_tables`, `_by_table`, `_active_target_counts` |
| `application/subscription/router.py` | `SubscriptionRouter.resolve()` |

## Server: less periodic and login-storm work

| Change | What it avoids |
|--------|----------------|
| **No 26 s OPTIONS loop** | Timer firing every 26 s across all systems to refresh static bridges when RPTO/startup/reload already handle it |
| **`ConfigPushThrottle`** | Flooding the monitor with CONFIG snapshots when many peers connect within a few seconds (debounce widens from ~0.3 s to ~2 s during bursts) |
| **`BoundedReportQueue`** | Doing pickle/JSON encode and TCP send synchronously on the voice hot path; coalesces duplicate config/bridge snapshots |

## Server: reporting and deployment

- **Report v2** — structured JSON replaces opaque pickle snapshots for bridge/config state on the **2.x monitor** wire. See [Monitoring and reports](../user-guide/monitoring.md) and [Report protocol v2](../protocols/report-v2.md).
- **Integrated proxy** — `PROXY` runs **in-process**; dropping the standalone **adn-proxy** saves baseline **RAM** (one interpreter, shared config) and simplifies ops.

## Monitor (adn-monitor 2.x)

Pair **adn-server 2.x** with **adn-monitor 2.x** to get the reporting-side gains:

| Change | Effect |
|--------|--------|
| **Slim wire / `dashboard_state`** | Monitor ingests compact JSON state instead of holding full duplicated pickle trees from v1 |
| **`clean_sys_dict`** | Periodic eviction of stale in-memory entries (caps runaway growth on long-lived panels) |
| **Last-heard row cache, lighter WS fingerprints** | Less work per dashboard refresh |
| **Unified FastAPI stack** | Removed separate PHP API and standalone monitor **proxy** process |

Details: [Monitor architecture](../../monitor/architecture.md).

## When you will notice a difference

| Deployment | CPU | RAM |
|------------|-----|-----|
| Few masters, no inject proxy, light traffic | Small | Small |
| **Inject-only proxy, many hotspots, busy TG** | **Clear** (downlink index) | Moderate (single server process vs server+proxy) |
| Long-lived monitor + report v2 | Moderate (less serialize on wire) | **Clearer** on monitor (slim state, `clean_sys_dict`) |

Crypto, AMBE, and OpenBridge MAC work still dominate on OpenBridge-heavy paths — routing-table optimizations do not remove that cost.

## Related reading

- [Architecture](architecture.md) — layers and entrypoint
- [BRIDGES vs Subscriptions](bridges-vs-subscriptions.md) — routing model (not a performance feature)
- [Behaviour and timers](behaviour-and-timers.md) — event-driven OPTIONS vs legacy 26 s loop
- [Hotspot proxy](../user-guide/hotspot-proxy.md) — integrated `PROXY` / inject-only
- [Report protocol v2](../protocols/report-v2.md) — JSON wire to monitor
- Release notes: `CHANGELOG.md` at the repository root (`Performance` under **2.0.0-rc.1**).
