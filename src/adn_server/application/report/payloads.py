"""Map runtime SYSTEMS / BRIDGES / BRDG_EVENT CSV to report JSON payloads (application layer)."""

from __future__ import annotations

import time
from typing import Any

from adn_server.domain import int_id

REPORT_PROTOCOL = 2
REPORT_FEATURES = (
    "INGRESS",
    "END_TX_FORWARD",
    "PUSH_ON_CONNECT",
    "REPORT_V2",
    "TOPOLOGY_JSON",
    "ROUTING_TABLE_JSON",
    "VOICE_EVENT_JSON",
    "DELTA_UPDATES",
)

_SYSTEM_MODES = frozenset({"MASTER", "PEER", "OPENBRIDGE"})
_TO_TYPES = frozenset({"ON", "OFF", "STAT", "NONE"})
_CSV_FAMILIES = {
    "GROUP VOICE": "GROUP",
    "PRIVATE VOICE": "PRIVATE",
    "UNIT DATA": "UNIT",
}


def _dmr_id(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int_id(value)


def _peer_connected(peer: dict[str, Any]) -> bool:
    return peer.get("CONNECTION") == "YES"


def _peer_field_json(value: Any) -> str | None:
    """Sanitize a legacy peer field for JSON (no secrets)."""
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace").strip()
        return text or None
    text = str(value).strip()
    return text or None


# Legacy CONFIG peer keys → topology JSON (display / lnksys classification).
_TOPOLOGY_PEER_FIELDS: tuple[tuple[str, str], ...] = (
    ("CALLSIGN", "callsign"),
    ("RX_FREQ", "rx_freq"),
    ("TX_FREQ", "tx_freq"),
    ("LOCATION", "location"),
    ("DESCRIPTION", "description"),
    ("URL", "url"),
    ("SLOTS", "slots"),
    ("PACKAGE_ID", "package_id"),
    ("SOFTWARE_ID", "software_id"),
    ("COLORCODE", "colorcode"),
    ("TX_POWER", "tx_power"),
)


def _topology_peer_row(peer_key: Any, peer: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": _dmr_id(peer_key),
        "connected": _peer_connected(peer),
    }
    if peer.get("IP"):
        row["ip"] = str(peer["IP"])
    if peer.get("PORT") is not None:
        row["port"] = int(peer["PORT"])
    for legacy_key, json_key in _TOPOLOGY_PEER_FIELDS:
        if legacy_key not in peer:
            continue
        text = _peer_field_json(peer[legacy_key])
        if text is not None:
            row[json_key] = text
    return row


def _system_has_connected_users(cfg: dict[str, Any]) -> bool:
    """True when an enabled system has at least one live peer or upstream link."""
    if not cfg.get("ENABLED", True):
        return False
    mode = cfg.get("MODE", "MASTER")
    if mode == "MASTER":
        return any(
            _peer_connected(peer)
            for peer in cfg.get("PEERS", {}).values()
            if isinstance(peer, dict)
        )
    if mode == "OPENBRIDGE":
        return any(
            _peer_connected(peer)
            for peer in cfg.get("PEERS", {}).values()
            if isinstance(peer, dict)
        )
    if mode in ("PEER", "XLXPEER"):
        for key in ("XLXSTATS", "STATS"):
            block = cfg.get(key)
            if isinstance(block, dict) and block.get("CONNECTION") == "YES":
                return True
        return False
    return False


def hello_connected_system_names(systems: dict[str, Any]) -> list[str]:
    """Enabled system names with connected users — optional HELLO hint (topology is authoritative)."""
    return sorted(
        name
        for name, cfg in systems.items()
        if isinstance(cfg, dict) and _system_has_connected_users(cfg)
    )


def build_topology(systems: dict[str, Any], *, seq: int, ts: float | None = None) -> dict[str, Any]:
    """Sanitized topology snapshot (no passphrases or runtime-only keys)."""
    epoch = time.time() if ts is None else ts
    out_systems: list[dict[str, Any]] = []
    for name, cfg in systems.items():
        if not isinstance(cfg, dict):
            continue
        mode = cfg.get("MODE", "MASTER")
        if mode not in _SYSTEM_MODES:
            mode = str(mode)
        entry: dict[str, Any] = {
            "name": name,
            "mode": mode,
            "enabled": bool(cfg.get("ENABLED", True)),
        }
        if cfg.get("IP"):
            entry["ip"] = str(cfg["IP"])
        port = cfg.get("PORT")
        if port is not None:
            entry["port"] = int(port)
        if "REPEAT" in cfg:
            entry["repeat"] = bool(cfg["REPEAT"])
        if cfg.get("ENHANCED_OBP"):
            entry["enhanced_obp"] = True
        if mode == "OPENBRIDGE" and cfg.get("NETWORK_ID") is not None:
            entry["network_id"] = _dmr_id(cfg["NETWORK_ID"])
        peers_out: list[dict[str, Any]] = []
        for peer_key, peer in cfg.get("PEERS", {}).items():
            if not isinstance(peer, dict):
                continue
            peers_out.append(_topology_peer_row(peer_key, peer))
        entry["peers"] = peers_out
        out_systems.append(entry)
    return {"type": "topology", "seq": int(seq), "ts": float(epoch), "systems": out_systems}


def build_routing_table(bridges: dict[str, Any], *, seq: int, ts: float | None = None) -> dict[str, Any]:
    """Routing table snapshot from BRIDGES."""
    epoch = time.time() if ts is None else ts
    routes: list[dict[str, Any]] = []
    for bridge_key, legs in bridges.items():
        if not isinstance(legs, list):
            continue
        leg_rows: list[dict[str, Any]] = []
        for leg in legs:
            if not isinstance(leg, dict):
                continue
            to_type = leg.get("TO_TYPE", "NONE")
            if to_type not in _TO_TYPES:
                to_type = str(to_type)
            row: dict[str, Any] = {
                "system": str(leg.get("SYSTEM", "")),
                "ts": int(leg.get("TS", 1)),
                "tgid": _dmr_id(leg.get("TGID", 0)),
                "active": bool(leg.get("ACTIVE", False)),
                "to_type": to_type,
            }
            timer = leg.get("TIMER")
            if timer is not None:
                row["timer_expires_at"] = float(timer)
            leg_rows.append(row)
        routes.append({"bridge_key": str(bridge_key), "legs": leg_rows})
    return {"type": "routing_table", "seq": int(seq), "ts": float(epoch), "routes": routes}


def parse_bridge_event_csv(event: str, *, ts: float | None = None) -> dict[str, Any] | None:
    """Parse legacy BRDG_EVENT CSV into a ``voice_event`` dict."""
    parts = [p.strip() for p in event.split(",")]
    if len(parts) < 9:
        return None
    call_family = _CSV_FAMILIES.get(parts[0])
    if call_family is None:
        return None
    phase = parts[1]
    direction = parts[2]
    try:
        stream_id = int(parts[4])
        peer_id = int(parts[5])
        src_id = int(parts[6])
        slot = int(parts[7])
        dst_id = int(parts[8])
    except (ValueError, IndexError):
        return None
    if slot not in (1, 2):
        return None
    if direction not in ("RX", "TX"):
        return None
    epoch = time.time() if ts is None else ts
    voice: dict[str, Any] = {
        "type": "voice_event",
        "ts": epoch,
        "call_family": call_family,
        "phase": phase,
        "direction": direction,
        "system": parts[3],
        "stream_id": stream_id,
        "peer_id": peer_id,
        "src_id": src_id,
        "slot": slot,
        "dst_id": dst_id,
    }
    if phase == "END" and len(parts) > 9:
        try:
            voice["duration_s"] = float(parts[9])
        except ValueError:
            voice["duration_s"] = None
    elif phase != "END":
        voice["duration_s"] = None
    return voice


def routing_table_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    seq: int,
    ts: float | None = None,
) -> dict[str, Any] | None:
    """Build a delta message when only some routes changed; ``None`` if unchanged."""
    if previous is None:
        return None
    prev_routes = {r["bridge_key"]: r for r in previous.get("routes", [])}
    changed: list[dict[str, Any]] = []
    for route in current.get("routes", []):
        key = route["bridge_key"]
        if prev_routes.get(key) != route:
            changed.append(route)
    if not changed:
        return None
    since_seq = int(previous.get("seq", 0))
    epoch = time.time() if ts is None else ts
    patch = {
        "type": "routing_table",
        "seq": int(seq),
        "ts": float(epoch),
        "routes": changed,
    }
    return {
        "type": "delta",
        "seq": int(seq),
        "ts": float(epoch),
        "since_seq": since_seq,
        "patch": patch,
    }


def topology_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    seq: int,
    ts: float | None = None,
) -> dict[str, Any] | None:
    """Build a delta when only some systems changed; ``None`` if unchanged."""
    if previous is None:
        return None
    prev_systems = {s["name"]: s for s in previous.get("systems", [])}
    changed: list[dict[str, Any]] = []
    for system in current.get("systems", []):
        name = system["name"]
        if prev_systems.get(name) != system:
            changed.append(system)
    if not changed:
        return None
    since_seq = int(previous.get("seq", 0))
    epoch = time.time() if ts is None else ts
    patch = {
        "type": "topology",
        "seq": int(seq),
        "ts": float(epoch),
        "systems": changed,
    }
    return {
        "type": "delta",
        "seq": int(seq),
        "ts": float(epoch),
        "since_seq": since_seq,
        "patch": patch,
    }
