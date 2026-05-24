# Talker Alias (DMR)

DMR **Talker Alias** (ETSI TS 102 361-2, 2016) carries a short alphanumeric label in the voice stream. On the Homebrew Protocol (HBP) it appears as separate **`DMRA`** UDP packets (15 bytes each, up to four per transmission).

This is **not** the same as subscriber ID aliases in `subscriber_ids.json` used for logs and the monitor UI. Talker Alias is embedded signaling intended for **radio displays** (OLED, Hytera/MD380tools, etc.).

See also: [Configuration](configuration.md#talker-alias-global).

---

## How ADN handles Talker Alias

When enabled on a **MASTER** system, the server can:

| Mode | Behaviour |
|------|-----------|
| **`both`** (default) | Pass through TA from the source hotspot/radio when all four `DMRA` blocks were received; otherwise inject from `subscriber_ids` + template. |
| **`passthrough`** | Relay buffered `DMRA` only. |
| **`inject`** | Always build TA from the configured template and alias data. |

On **bridge forward** at voice header (`VHEAD`), the server sends four `DMRA` packets to each HBP target (**MASTER** peers or **PEER** upstream) once per stream, then forwards `DMRD` as usual.

**MMDVMHost / DMRGateway (Pi-Star, WPSD):** stock MMDVMHost does **not** consume standalone downlink `DMRA` UDP; it decodes Talker Alias from **embedded LC inside `DMRD` voice** (FLCO 4–7). When TA is enabled, ADN injects TA into the embedded LC of voice bursts **B–E** (dtype 1–4) on **bridge forward** to HBP targets, in addition to optional standalone `DMRA` packets for clients that support them.

On the **same MASTER**, when **`REPEAT`** copies group voice to other logged-in hotspots, the server also sends those four `DMRA` packets on `VHEAD` (excluding the transmitting peer). Bridge forwarding to the same system shares the same once-per-stream dedupe, so TA is not sent twice.

**Not supported:** OpenBridge legs (no standard `DMRA` on OBP/DMRE wire). Legacy ADN never implemented TA beyond debug logging.

---

## Configuration

Under **`GLOBAL`** (optional per-system override with the same keys):

```yaml
GLOBAL:
  TALKER_ALIAS: false
  TALKER_ALIAS_MODE: both
  TALKER_ALIAS_FORMAT: "{callsign} {fname}"
```

| Key | Meaning |
|-----|---------|
| **TALKER_ALIAS** | Master switch (`false` by default). |
| **TALKER_ALIAS_MODE** | `both`, `passthrough`, or `inject`. Default **`both`** if omitted. |
| **TALKER_ALIAS_FORMAT** | Python format string; fields: `{callsign}`, `{fname}`, `{surname}`, `{id}`. |

Maximum string length is **29 characters** (ETSI / MMDVMHost). This limit is fixed in code and is **not** configurable, to avoid incompatible payloads on radios and hotspots.

Subscriber JSON may include `fname`, `surname`, or a dedicated `talker_alias` field per record.

---

## HBP `DMRA` wire format

| Offset | Field |
|--------|--------|
| 0–3 | `DMRA` |
| 4–6 | Source DMR ID (3 bytes, big-endian) |
| 7 | Block index 0–3 |
| 8–14 | 7 payload bytes |

Encoding uses **UTF-8 format** (format 2), matching MMDVMHost `DMRTA.cpp`.

Embedded TA in `DMRD` voice alternates superframes: one cycle (bursts B–E) with the normal group embedded LC, the next with a TA block (FLCO 4–7), repeating until the stream ends.

---

## Pi-Star / MMDVM operator settings

For TA to reach the **local RF radio**:

| Setting | Recommendation |
|---------|----------------|
| **DMR DumpTAData** | `1` (on, Pi-Star default): write embedded Talker Alias to the MMDVM log — required for Pi-Star dashboard / log-based tools to show TA; with `0` nothing appears there. This does **not** block TA on RF. |
| **DMR EmbeddedLCOnly** | `off` (default). If `on`, Talker Alias from the network is disabled. |

Pi-Star’s web dashboard does not show TA; use the radio OLED, MD380tools, or tools such as [pistar-lastqso](https://github.com/kencormack/pistar-lastqso).

**Radio compatibility:** Hytera PD6/7/9 and MD380tools firmware generally work. Many Motorola radios do not support TA; some older firmware may show audio issues when TA is present.

The **adn-monitor proxy** already forwards `DMRA` to the master unchanged.

---

## Limitations and follow-up work

| Topic | Status |
|-------|--------|
| TA on **OpenBridge** targets | Not available (no `DMRA` on standard OBP wire). |
| **Monitor dashboard** live TA column | Separate work (monitor uses DB aliases, not live `DMRA`). |
| Unrelated **`RuntimeError`** in bridge iteration | Tracked as a separate fix. |

---

## References

- [ETSI TS 102 361-2](http://www.etsi.org/deliver/etsi_ts/102300_102399/10236102/02.03.01_60/ts_10236102v020301p.pdf) (Talker Alias format)
- [MMDVMHost `DMRTA.cpp`](https://github.com/g4klx/MMDVMHost/blob/master/DMRTA.cpp) / [`DMRNetwork.cpp`](https://github.com/g4klx/MMDVMHost/blob/master/DMRNetwork.cpp) (`writeTalkerAlias`)
