# Performance (2.x)

**adn-server 2.x** and **adn-monitor 2.x** use less CPU and RAM than **adn-dmr-server**
and the old monitor/proxy stack. You do not need to tune anything — the gains come from
how routing, reporting, and the integrated proxy are built.

Pair **server 2.x with monitor 2.x** to get the full benefit on the dashboard side.

## What improved

| Improvement | What you get |
|-------------|--------------|
| **Smarter voice routing** | Under busy group traffic the server does less work per packet — especially on proxies with many hotspots and on OpenBridge-heavy nodes. |
| **Integrated hotspot proxy** | One `adn-server` process instead of server + standalone **adn-proxy** — less RAM and simpler ops. See [Hotspot proxy](../user-guide/hotspot-proxy.md). |
| **No legacy 26 s timer** | Static talkgroups refresh on events (startup, config reload, peer OPTIONS), not a background loop every 26 seconds. See [Behaviour and timers](behaviour-and-timers.md). |
| **Lighter monitor link** | **Report v2** sends compact JSON instead of heavy periodic pickle dumps. See [Report protocol v2](../protocols/report-v2.md). |
| **Monitor 2.x** | Slimmer dashboard state, less memory growth on panels left open for days. See [Monitor architecture](../../monitor/architecture.md). |

## OpenBridge-heavy servers (2.3.3+)

If you run **many OpenBridges** and upgrade from an earlier **2.x** build to **2.3.3 or
newer**, a production node under comparable OBP load showed roughly:

| | Before (2.x) | After (2.3.3+) |
|--|--------------|----------------|
| **CPU** | baseline | **~25% of before** |
| **RAM** | baseline | **~75% of before** |

Exact numbers depend on traffic and hardware; treat these as a reference, not a guarantee.

## When you will notice it most

| Your network | Effect |
|--------------|--------|
| Small install, few peers, light traffic | Modest — the stack is simply lighter overall. |
| **Inject proxy with many hotspots** | **Clear CPU win** when group voice is busy. |
| **Many OpenBridges, steady mesh traffic** | **Clear CPU and RAM win** after **2.3.3+** (see table above). |
| **Many hotspots logging in at once** | Less load on server and monitor during login bursts. |
| **Monitor open 24/7** | Lower and more stable RAM on **adn-monitor 2.x**. |

Crypto, AMBE, and OpenBridge wire work still cost CPU on busy OBP paths — routing
optimizations remove redundant bridge work, not voice codec or encryption overhead.

## Related reading

- [Hotspot proxy](../user-guide/hotspot-proxy.md) — integrated `PROXY`
- [Monitoring and reports](../user-guide/monitoring.md) — report v2 pairing
- [Behaviour and timers](behaviour-and-timers.md) — event-driven OPTIONS
- Release notes: `CHANGELOG.md` at the repository root
