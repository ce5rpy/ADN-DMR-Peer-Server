# Configuration

## Files and workflow

| File | Committed | Role |
|------|-----------|------|
| `adn-server.example.yaml` | Yes | Template — copy to `adn-server.yaml` and edit. |
| `adn-server.yaml` | **No** (gitignored) | Main server: systems, globals, logging, aliases, reports. |
| `adn-voice.example.yaml` | Yes | Template for voice — copy to `adn-voice.yaml`. |
| `adn-voice.yaml` | **No** (typical) | Voice/TTS/recording; merged into `config["VOICE"]` at startup and **hot-reloaded** (~every 15 s) if the file changes. |

Run:

```bash
python adn-server.py -c /path/to/adn-server.yaml
```

Optional: `--logging LEVEL` overrides `LOGGER.LOG_LEVEL`.

If `adn-voice.yaml` sits next to `adn-server.yaml`, it is loaded automatically. You can also put a `VOICE:` block inside `adn-server.yaml`; the separate file is the usual way to change announcements without touching the main config.

**Secrets:** Never commit real passphrases, security URLs, or `user_passwords.json` / `encryption_key.secret`. Use placeholders in templates and keep production files local.

---

## Architecture: what is a “system”?

Each entry under **`SYSTEMS`** is a named **logical link** (UDP endpoint) that speaks **HBP** (HomeBrew Protocol) to hotspots/repeaters, or **OpenBridge** to other servers. Names are free-form strings (`SYSTEM`, `ECHO`, `OBP-UK`, …) and are used in logs and in the **bridge table** (`BRIDGES`) to identify where traffic enters or leaves.

Three **modes** exist:

| Mode | Typical use | Listens | Connects upstream |
|------|-------------|---------|-------------------|
| **MASTER** | Conference server for one or more hotspots/repeaters | **Yes** — `IP` / `PORT`, peers register with passphrase | No (peers connect to you) |
| **PEER** | Hotspot/repeater or service (e.g. parrot) behaving as a **client** of a MASTER | **Yes** — local `IP` / `PORT` | **Yes** — `MASTER_IP` / `MASTER_PORT` must point at a MASTER |
| **OPENBRIDGE** | Link to another **server** over OpenBridge (DMRD v1 / DMRE) | **Yes** — `IP` / `PORT` | **Yes** — `TARGET_IP` / `TARGET_PORT` (peer server) |

**MASTER** holds the **`PEERS`** table at runtime (hotspots that authenticated). **PEER** maintains **STATS** (connection, pings). **OPENBRIDGE** uses **NETWORK_ID**, **PASSPHRASE**, **TARGET_***, **PROTO_VER** / **VER**, and optional **ENHANCED_OBP**, **RELAX_CHECKS**, **TGID_ACL**.

A single process can run **several** systems at once (e.g. one MASTER for users, one ECHO for parrot, one OBP to a partner network).

---

## `GLOBAL`

Server-wide defaults. Many keys can be overridden per system if `USE_ACL` (or similar) is set on that system.

| Key | Meaning |
|-----|---------|
| **PING_TIME** | Interval (seconds) for PEER keepalive / ping logic toward MASTER. |
| **MAX_MISSED** | How many missed pings before treating the PEER link as unhealthy (depends on implementation with STATS). |
| **USE_ACL** | If true, **REG_ACL**, **SUB_ACL**, **TGID_TS1_ACL**, **TGID_TS2_ACL** are applied (after processing into internal tuples). |
| **REG_ACL** | Access control for **registration** / peer IDs (`PERMIT:…` / `DENY:…`; see [ACL strings](#acl-strings)). |
| **SUB_ACL** | ACL for **subscriber** (radio) IDs on received traffic. |
| **TGID_TS1_ACL** | ACL for **talkgroup** on **timeslot 1**. |
| **TGID_TS2_ACL** | ACL for **talkgroup** on **timeslot 2**. |
| **GEN_STAT_BRIDGES** | If true, OpenBridge can trigger creation of **static** bridge rows for certain TGs (see [Bridges and talkgroups](bridges-and-talkgroups.md)). |
| **SERVER_ID** | Numeric server ID; stored as 4-byte value for OpenBridge / voice metadata. |
| **VALIDATE_SERVER_IDS** | If true (DMRE path), **source server** IDs may be checked against a downloaded list (`ALIASES` **SERVER_ID_**\*). |
| **URL_SECURITY** / **PORT_SECURITY** / **PASS_SECURITY** | If set, enables download of keys/password material from the security endpoint (see example comments). Empty = disabled. |
| **USERS_PASS** | Filename for per-radio password JSON (optional). |
| **HASH_ENCRYPT** | Path to encryption key for password file handling. |

---

## `SYSTEMS` — common fields

These appear mainly on **MASTER** (and often on **PEER**). OpenBridge uses a different subset.

| Key | Meaning |
|-----|---------|
| **MODE** | `MASTER`, `PEER`, or `OPENBRIDGE`. |
| **ENABLED** | If `false`, the system is skipped. |
| **IP** / **PORT** | UDP bind address for this system’s HBP or OpenBridge listener. |
| **PASSPHRASE** | Shared secret for HBP authentication (MASTER ↔ PEER). Must match between a PEER and its MASTER. |
| **USE_ACL** | Per-system ACL override when true (uses system-level `REG_ACL` / `SUB_ACL` / `TGID_TS*_ACL`). |
| **GROUP_HANGTIME** | Hang time (seconds) for group voice state. |
| **DEFAULT_UA_TIMER** | Default timeout (minutes in many places) for **user-activated** bridges. |
| **ANNOUNCEMENT_LANGUAGE** | Default language folder under `Audio/<lang>/` for prompts on this system. |
| **ALLOW_UNREG_ID** | Whether unregistered subscriber IDs are allowed (MASTER). |

---

## `SYSTEMS` — MASTER

| Key | Meaning |
|-----|---------|
| **REPEAT** | If true, received traffic can be **repeated** to other connected peers on the MASTER (typical conference behaviour). |
| **MAX_PEERS** | Maximum connected hotspots. |
| **EXPORT_AMBE** | Feature flag for AMBE export (if enabled in build). |
| **SINGLE_MODE** | Affects OPTIONS / generator expansion (single-user style). |
| **VOICE_IDENT** | Enables periodic **voice ident** when conditions are met (see `IdentUseCases`). |
| **TS1_STATIC** / **TS2_STATIC** | Comma-separated static TG lists pushed via OPTIONS handling (see `options_config`). |
| **DEFAULT_REFLECTOR** | Default **reflector** number for `#` dial bridges (0 = none). |
| **OVERRIDE_IDENT_TG** | Optional TG for voice ident instead of all-call. |
| **GENERATOR** | If **> 1**, this MASTER is expanded into **`NAME-0`**, **`NAME-1`**, … with consecutive ports (see `expand_generator` in code). |

**MASTER** listens for PEER connections; each authenticated peer is stored under **`PEERS`** at runtime.

---

## `SYSTEMS` — PEER

A **PEER** connects **outbound** to a **MASTER** and listens locally for the radio or app.

| Key | Meaning |
|-----|---------|
| **MASTER_IP** / **MASTER_PORT** | Address of the **MASTER** to register with (must match that MASTER’s `IP`/`PORT`). |
| **RADIO_ID** | This peer’s ID in HBP (4-byte). |
| **CALLSIGN**, **RX_FREQ**, **TX_FREQ**, **COLORCODE**, **LATITUDE**, … | RPT payload fields sent to the MASTER during registration (fixed widths in protocol). |
| **OPTIONS** | Byte string / options line (e.g. `TS2=9990;`) for static TG / behaviour. |
| **LOOSE** | Relaxed handling flag where applicable. |

The **parrot** example (`adn-parrot.example.yaml`) is a PEER that attaches to the **ECHO** MASTER: same **PASSPHRASE**, **MASTER_PORT** = ECHO’s **PORT**. See [Parrot](parrot.md).

---

## `SYSTEMS` — OPENBRIDGE

| Key | Meaning |
|-----|---------|
| **NETWORK_ID** | Must match the peer’s **NETWORK_ID** in OpenBridge packets. |
| **TARGET_IP** / **TARGET_PORT** | Remote OpenBridge peer (UDP). |
| **TGID_ACL** (or **TG1_ACL**) | Talkgroup ACL for OpenBridge (often `DENY:0-82,…` style ranges). |
| **RELAX_CHECKS** | Allow packets when peer socket does not match `TARGET` strictly (use with care). |
| **ENHANCED_OBP** | Enables **BCSQ** / **BCKA** and multi-path loop control — **should be `true`** for ADN Systems inter-server links (see below). |
| **PROTO_VER** | Embedded **DMRE** protocol version; **`5`** selects **DMRE / OpenBridge v5** (89-byte frame, BLAKE2b). Default in code is **5**; use **5** for new ADN deployments. |

**ADN Systems recommendation:** For every OpenBridge peer in the ADN mesh, set **`PROTO_VER: 5`** (DMRE v5) and **`ENHANCED_OBP: true`**. Align the same settings on **both** ends. Older **DMRD v1**-only peers are possible for backward compatibility but are not the recommended mode for the network.

Ingress filters and loop control: [OpenBridge protocol](../protocols/openbridge.md) (including [DMRE vs OpenBridge v5](../protocols/openbridge.md#dmre-and-openbridge-v5)) and [Special numbers — OpenBridge ingress](special-numbers.md#openbridge-ingress--group-tg-filters).

---

## `BRIDGES` (runtime)

The **bridge table** maps TG keys to routing rows. It is **in memory** for the running process.

The YAML loader does **not** load a top-level `BRIDGES:` block from `adn-server.yaml` into the router today — initial rows are created in code (e.g. **9990 / ECHO** bootstrap when an **ECHO** system exists), then **OPTIONS**, **user-activated** bridges, **static** bridges, and **OpenBridge** logic add rows over time.

For the conceptual model (ACTIVE, TS, TGID, timeouts): [Bridges and talkgroups](bridges-and-talkgroups.md).

---

## `REPORTS`

TCP report channel for **adn-monitor** (or compatible dashboards).

| Key | Meaning |
|-----|---------|
| **REPORT** | Enable/disable sending. |
| **REPORT_INTERVAL** | Periodic push interval (seconds). |
| **REPORT_PORT** | Local port the **server listens on** for report clients. |
| **REPORT_CLIENTS** | Comma-separated or list of allowed client IPs (see example). |

Details: [Monitoring and reports](monitoring.md).

---

## `LOGGER`

Implemented in `infrastructure/logging_config.py` (`setup_logging`). Values are read from the **`LOGGER`** block (or overridden by `--logging` for **LOG_LEVEL** only).

| Key | Meaning |
|-----|---------|
| **LOG_HANDLERS** | Comma-separated list of handler **tokens** (whitespace around commas is fine). Each token selects outputs; you can combine several. Recognised values: **`console-timed`** or **`console`** — log to **stderr** with format `LEVEL asctime message`; **`file-timed`** or **`file`** — log to **LOG_FILE** with the same format (UTF-8). **Default** if omitted: `console-timed`. Examples: `console-timed` only; `file-timed` only; `console-timed,file-timed` for both console and file. |
| **LOG_FILE** | Path used when **`file-timed`** or **`file`** is in **LOG_HANDLERS**. If missing, the code defaults to `/dev/null`. If the path is **`/dev/null`**, file handlers are **not** attached even if listed. If the file cannot be opened (permissions, missing directory), a warning is written to stderr and logging continues without that file handler. |
| **LOG_LEVEL** | Root logger level: **`DEBUG`**, **`INFO`**, **`WARNING`**, **`ERROR`**, **`CRITICAL`** (case-insensitive; default **INFO**). Unknown names fall back to **INFO**. You can override at startup with **`python adn-server.py --logging LEVEL`** (same names). A custom **`TRACE`** level is registered for occasional `logger.trace(...)` calls; use **`DEBUG`** for verbose diagnostics in normal operation. |
| **LOG_NAME** | Name of the logger returned to the application (default **`ADN`**). Does not change the list of handlers; it selects which named logger gets the configured level. |

---

## `ALIASES`

Downloads and local files for **peer IDs**, **subscriber IDs**, **talkgroup labels**, optional **server ID list**, **checksums**, and **keys**. Used for dashboards, validation, and optional security downloads.

| Key | Meaning |
|-----|---------|
| **PATH** | Base directory for JSON/TSV/pickle files. |
| **TRY_DOWNLOAD** | Whether to fetch from URLs when stale. |
| **PEER_FILE** / **SUBSCRIBER_FILE** / **TGID_FILE** | Local filenames. |
| **\*_URL** | Remote sources for downloads. |
| **SUB_MAP_FILE** | Pickle path for **SUB_MAP** (private call routing); default name if empty. |
| **STALE_DAYS** | Refresh threshold for downloads. |

---

## `VOICE` (from `adn-voice.yaml` or inline)

Merged into `config["VOICE"]`. See [Voice, announcements, and TTS](voice-and-tts.md) and `adn-voice.example.yaml`.

---

## ACL strings

Processed by `acl_build`: `PERMIT:` or `DENY:` followed by comma-separated IDs or ranges.

Examples:

- `PERMIT:ALL` — allow all IDs in range.
- `DENY:1` — deny ID 1 only.
- `DENY:0-82,9990-9999` — deny listed ranges.

Global ACLs apply when `USE_ACL` is true; OpenBridge may use **TGID_ACL** on the OBP system.

---

## Python environment

Use the project interpreter (see workspace rules), e.g. `python3.11` from pyenv, for consistent behaviour with production.

---

## See also

- [Introduction](introduction.md) — role of the server.
- [Bridges and talkgroups](bridges-and-talkgroups.md) — `BRIDGES` semantics.
- [Special numbers](special-numbers.md) — reserved TGs and server IDs.
- [Parrot](parrot.md) — PEER example (parrot process).
