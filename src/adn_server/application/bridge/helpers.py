# ADN DMR Peer Server - bridge helpers (V2-P0-004)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Shared bridge routing helpers (no Twisted)."""

from __future__ import annotations

from typing import Any

from ...domain import bytes_3, bytes_4, int_id

# Embedded LC codeword sits at bits 116:148 inside the 48-bit EMB field (108:156).
# Legacy bridge_master.py replaces dmrbits[116:148] on bursts B–E (dtype_vseq 1–4).
EMB_LC_SLICE = slice(116, 148)


def obp_target_bcsq_quenches_stream(
    systems_cfg: dict[str, Any], target_name: str, dst_id_b: bytes, stream_id: bytes
) -> bool:
    """True if target OBP config has _bcsq[tgid]==stream_id (bytes key or same int TG)."""
    m = systems_cfg.get(target_name, {}).get("_bcsq")
    if not isinstance(m, dict) or not m:
        return False
    tid = dst_id_b[:3] if isinstance(dst_id_b, bytes) and len(dst_id_b) >= 3 else bytes_3(int_id(dst_id_b))
    if m.get(tid) == stream_id:
        return True
    for k, v in m.items():
        if v != stream_id:
            continue
        try:
            if isinstance(k, bytes) and len(k) >= 3 and int_id(k) == int_id(tid):
                return True
        except Exception:
            continue
    return False


def _peer_key_from_int(peer_key: Any) -> bytes:
    if isinstance(peer_key, bytes):
        return peer_key
    if isinstance(peer_key, int):
        return bytes_4(peer_key)
    if isinstance(peer_key, str) and peer_key.isdigit():
        return bytes_4(int(peer_key))
    return bytes_4(int_id(peer_key))


def _fuzzy_peer_matches(
    val: int,
    peers: dict[Any, Any],
) -> list[bytes]:
    val_str = str(val)
    matches: list[bytes] = []
    for pk in peers:
        try:
            pk_b = _peer_key_from_int(pk)
        except (TypeError, ValueError):
            continue
        pk_int = int_id(pk_b)
        pk_str = str(pk_int)
        if pk_int == val or pk_int // 100 == val:
            matches.append(pk_b)
            continue
        if len(val_str) >= 5 and len(pk_str) >= 7 and pk_str.startswith(val_str):
            matches.append(pk_b)
    return matches


def resolve_voice_peer_id(
    peer_id: bytes,
    rf_src: bytes,
    system_name: str,
    systems_cfg: dict[str, Any],
) -> bytes:
    """Resolve BRDG_EVENT field 5 for RX legs from a MASTER (hotspot transmitting).

    Legacy bridge uses ``_peer_id`` from DMRD for TX legs unchanged. Only RX source
    events need the full hotspot radio id so monitor ``rts_update`` marks that peer RX.
    """
    peers = systems_cfg.get(system_name, {}).get("PEERS", {})
    if not isinstance(peers, dict) or not peers:
        return peer_id
    peer_b = peer_id if isinstance(peer_id, bytes) else bytes_4(int_id(peer_id))
    if peer_b in peers:
        return peer_b
    rf_b = rf_src if isinstance(rf_src, bytes) else bytes_3(int_id(rf_src))
    if rf_b in peers:
        return rf_b
    peer_matches = _fuzzy_peer_matches(int_id(peer_id), peers)
    if len(peer_matches) == 1:
        return peer_matches[0]
    rf_matches = _fuzzy_peer_matches(int_id(rf_src), peers)
    if len(rf_matches) == 1:
        return rf_matches[0]
    return peer_id


# Back-compat alias for tests and imports.
report_peer_id_for_hbp_target = resolve_voice_peer_id


def is_special_tg(bridge_key: str) -> bool:
    """True if bridge is special TGID 9990-9999 (excluded from infinite timer)."""
    if bridge_key and bridge_key[0:1] == "#":
        return False
    try:
        return 9990 <= int(bridge_key) <= 9999
    except ValueError:
        return False


def parse_dmrd_route_fields(packet: bytes) -> tuple[int, int, str] | None:
    """Parse HBP DMRD slot, destination TG, and call type for downlink OPTIONS filter."""
    if len(packet) < 17 or packet[:4] != b"DMRD":
        return None
    bits = packet[15]
    slot = 2 if (bits & 0x80) else 1
    if bits & 0x40:
        call_type = "unit"
    elif (bits & 0x23) == 0x23:
        call_type = "vcsbk"
    else:
        call_type = "group"
    return slot, int_id(packet[8:11]), call_type


def peer_receives_group_tgid(peer: dict[str, Any], slot: int, tgid: int) -> bool:
    """True when peer RPTO OPTIONS list the group TG on that voice timeslot."""
    from adn_server.application.report.payloads import parse_peer_options_static

    ts1, ts2 = parse_peer_options_static(peer.get("OPTIONS"))
    static = ts1 if slot == 1 else ts2
    if not static:
        return False
    return str(tgid) in static


def peer_matches_rf_source(peer_id: bytes, rf_src: bytes, peers: dict[Any, Any]) -> bool:
    """True when a hotspot radio id matches the voice RF source (parrot / echo downlink)."""
    peer_b = _peer_key_from_int(peer_id)
    return peer_b in _fuzzy_peer_matches(int_id(rf_src), peers)
