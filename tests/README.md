# Test layout

One **topic per file** — run only what you need while developing or validating a change.

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest tests/<path>/test_<name>.py -q          # single file
python3 -m pytest tests/<path>/test_<name>.py::test_foo -q # single test
python3 -m pytest tests/bridge/ -q                         # whole domain
python3 -m pytest tests/ -q                                # full suite (152)
```

Use the project interpreter, e.g. `/opt/.pyenv/versions/3.11.8/bin/python3`.

## Directories

| Directory | What it covers |
|-----------|----------------|
| `bridge/` | Static TG, startup bridges, unit data, CRC dedup, echo, private voice, config reload |
| `hbp/` | HBP ingress, loop control, rate limit, timeout/collision, master maintenance |
| `obp/` | OpenBridge loop, rate limit, unit-data loop |
| `voice/` | Announcements, TTS schedule, broadcast queue, disconnected voice, in-band signalling |
| `talker_alias/` | Encode/decode, passthrough, MMDVM wire, bridge inject |
| `parrot/` | Recording timers, playback loop, seq preservation, ingress path |
| `smoke/` | Quick routing smoke + packet builder |
| `infrastructure/` | Logging reload, bridge router index |
| `application/` | RuntimeContext holder / config proxy |
| `scripts/` | Config conversion helpers |
| `harness/` | Shared fakes (`DeterministicScenario`, assertions) — not run as tests |

## Files by domain

### bridge/

| File | Tests | Topic |
|------|-------|-------|
| `test_config_reload.py` | 1 | Merge system config on reload |
| `test_crc_dedup.py` | 3 | HBP/OBP CRC dedup, seq=0 |
| `test_echo_bridgereset.py` | 5 | Echo leg after BRIDGERESET / OPTIONS |
| `test_options_config_loop.py` | 2 | 26s OPTIONS static TG |
| `test_private_voice.py` | 3 | Private call routing |
| `test_startup_bridges.py` | 4 | Startup BRIDGES + voice E2E |
| `test_static_tg_options.py` | 4 | Static TG from peer OPTIONS |
| `test_unit_data_ingress.py` | 4 | Unit headers, CSBK, reports |
| `test_unit_data_routing.py` | 5 | SUB_MAP, hotspot, gateway, OBP fanout |

### hbp/

| File | Tests | Topic |
|------|-------|-------|
| `test_hbp_loop_control.py` | 2 | HBP loop winner/loser |
| `test_hbp_rate_limit.py` | 2 | Ingress rate drop + stall |
| `test_ingress.py` | 3 | RX start, rate drop, OBP loop loser |
| `test_master_maintenance.py` | 2 | Peer timeout / shared PEERS dict |
| `test_timeout_collision.py` | 3 | 180s timeout, collision, rekey |

### obp/

| File | Tests | Topic |
|------|-------|-------|
| `test_loop_control.py` | 4 | OBP loop, VTERM, BCSQ |
| `test_obp_rate_limit.py` | 1 | Rate limit epoch |
| `test_unit_data_loop.py` | 2 | Unit data loop loser |

### voice/

| File | Tests | Topic |
|------|-------|-------|
| `test_announcement_anticollision.py` | 3 | Busy slot skip / abort |
| `test_broadcast_queue.py` | 2 | Same-TG broadcast queue |
| `test_disconnected_voice.py` | 3 | Not-linked / reflector prompts |
| `test_embed_ta_forward.py` | 2 | Embed TA state on bridge |
| `test_in_band_signalling.py` | 5 | Reflector / single-mode VTERM |
| `test_play_file_on_request.py` | 3 | On-demand file playback |
| `test_scheduled_announcement.py` | 4 | File announcements (AMBE) |
| `test_scheduled_tts.py` | 7 | TTS schedule + conversion |
| `test_voice_config_reload.py` | 3 | Hot reload announcement/TTS loops |

### talker_alias/

| File | Tests | Topic |
|------|-------|-------|
| `test_bridge_inject.py` | 5 | TA inject on bridge VHEAD |
| `test_embed_ta.py` | 4 | Embedded LC modes |
| `test_encode_decode.py` | 8 | Domain encode/decode |
| `test_format.py` | 2 | Format from subscriber profile |
| `test_mmdvm_wire.py` | 10 | MMDVM wire blocks |
| `test_passthrough.py` | 9 | Passthrough / both modes |

### parrot/

| File | Tests | Topic |
|------|-------|-------|
| `test_playback_ingress.py` | 2 | `ingress_pkt_time`, record→playback |
| `test_playback_logging.py` | 1 | Duration log format |
| `test_playback_send_loop.py` | 4 | Send loop, max duration, interval |
| `test_recording_timers.py` | 2 | Idle timeout, VTERM commit |
| `test_rekey_playback.py` | 4 | Seq preservation past 255 / 30s |

### smoke/ · infrastructure/ · scripts/

| File | Tests | Topic |
|------|-------|-------|
| `smoke/test_bridge_routing.py` | 1 | Static TG forward smoke |
| `smoke/test_packet_builder.py` | 1 | PacketSpec builder |
| `infrastructure/test_logging_reload.py` | 2 | Log level reload |
| `infrastructure/test_bridge_router_index.py` | 5 | BRIDGES O(1) index vs legacy scan |
| `application/test_runtime_context.py` | 5 | RuntimeContext holder, SIGHUP swap prep |
| `scripts/test_freedmr_cfg_to_yaml.py` | 5 | Legacy cfg → YAML |

## Examples (copy-paste)

```bash
# After changing bridge unit-data routing
python3 -m pytest tests/bridge/test_unit_data_routing.py -q

# After parrot seq fix
python3 -m pytest tests/parrot/test_rekey_playback.py -q

# HBP loop + rate (common RF regressions)
python3 -m pytest tests/hbp/test_hbp_loop_control.py tests/hbp/test_hbp_rate_limit.py -q

# One test by name
python3 -m pytest tests/bridge/test_startup_bridges.py::test_startup_bridge_routes_voice_after_apply -q
```

## Policy

- **New tests:** add a new file (or extend the smallest existing file for the same topic). Avoid large multi-topic modules.
- **Harness:** shared code lives in `harness/` only.
- Full audit: `docs-priv/en/test-audit.md` (maintainer checkout).
