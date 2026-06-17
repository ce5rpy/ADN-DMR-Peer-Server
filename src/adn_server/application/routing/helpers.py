# ADN DMR Peer Server - bridge helpers
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
###############################################################################
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
###############################################################################
#
# Derived from ADN DMR Server / FreeDMR / HBlink. Original license:
###############################################################################
# Copyright (C) 2026 Joaquin Madrid Belando, EA5GVK <ea5gvk@gmail.com>
# Copyright (C) 2020 Simon Adlem, G7RZU <g7rzu@gb7fr.org.uk>
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS <n0mjs@me.com>
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
###############################################################################

"""Shared bridge routing helpers (no Twisted)."""

from __future__ import annotations

import time
from typing import Any

from ...domain import HBPF_DATA_SYNC, HBPF_SLT_VHEAD, bytes_3, bytes_4, int_id


def is_private_subscriber_dst(dst_id: bytes) -> bool:
    """True for 7-digit private/unit destinations (legacy routerHBP pvt_call branch)."""
    return len(str(int_id(dst_id))) == 7


def unit_data_hbp_target_idle(
    dst_slot: dict,
    pkt_time: float,
    hangtime: float,
) -> bool:
    """Legacy sendDataToHBP gate: both RX/TX idle and past group hangtime."""
    from ...domain.hbp_protocol import HBPF_SLT_VTERM

    return (
        dst_slot.get("RX_TYPE") == HBPF_SLT_VTERM
        and dst_slot.get("TX_TYPE") == HBPF_SLT_VTERM
        and (pkt_time - dst_slot.get("TX_TIME", 0) > hangtime)
    )


def is_unit_data_ingress(
    call_type: str,
    dtype_vseq: int,
    stream_id: bytes,
    slot_rx_stream_id: bytes | None,
) -> bool:
    """True when legacy routerHBP sets ``_data_call`` (bridge_master.py ~3130).

    Unit data is routed but must not update per-slot RX STATUS (busy check for
    downlink SUB_MAP / hotspot match stays open on the source MASTER).
    """
    if call_type != "unit":
        return False
    if dtype_vseq in (6, 7, 8):
        return True
    if dtype_vseq == 3:
        return stream_id != (slot_rx_stream_id or b"\x00")
    return False


# Embedded LC codeword sits at bits 116:148 inside the 48-bit EMB field (108:156).
# Legacy bridge_master.py replaces dmrbits[116:148] on bursts B–E (dtype_vseq 1–4).
EMB_LC_SLICE = slice(116, 148)


def tg4000_reset_on_vhead(int_dst_id: int, frame_type: int, dtype_vseq: int) -> bool:
    """True when TG/ID 4000 voice header should trigger a one-shot dynamic reset."""
    return (
        int_dst_id == 4000
        and frame_type == HBPF_DATA_SYNC
        and dtype_vseq == HBPF_SLT_VHEAD
    )


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


def is_special_tg(relay_table_key: str) -> bool:
    """True if bridge is special TGID 9990-9999 (excluded from infinite timer)."""
    if relay_table_key and relay_table_key[0:1] == "#":
        return False
    try:
        return 9990 <= int(relay_table_key) <= 9999
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


def _system_has_active_bridge_leg(
    bridges: dict[str, Any] | None,
    system: str,
    slot: int,
    tgid: int,
    *,
    subscription_store: Any | None = None,
) -> bool:
    """True when the store (or legacy BRIDGES export) has an ACTIVE leg for ``(system, slot, tgid)``."""
    if subscription_store is not None and system:
        from adn_server.application.subscription.subscription_queries import (
            system_has_active_leg_in_store,
        )

        return system_has_active_leg_in_store(subscription_store, system, slot, tgid)
    if not bridges or not system:
        return False
    legs = bridges.get(str(tgid))
    if not isinstance(legs, list):
        return False
    for leg in legs:
        if not isinstance(leg, dict) or not leg.get("ACTIVE"):
            continue
        if str(leg.get("SYSTEM", "")) != system:
            continue
        if int(leg.get("TS", 0)) != int(slot):
            continue
        return True
    return False


def peer_options_fields(peer: dict[str, Any]) -> dict[str, Any]:
    """Parse hotspot OPTIONS into fields used by SINGLE/TIMER resolution."""
    from adn_server.application.report.payloads import parse_peer_options_fields

    return parse_peer_options_fields(peer.get("OPTIONS"))


def _peer_ua_session_entry(
    sys_cfg: dict[str, Any],
    peer_id: bytes | None,
    slot: int,
) -> dict[str, Any] | None:
    if peer_id is None:
        return None
    store = sys_cfg.get("_PEER_UA_SESSIONS")
    if not isinstance(store, dict):
        return None
    pk = bytes_4(int_id(peer_id))
    per_peer = store.get(pk)
    if not isinstance(per_peer, dict):
        return None
    entry = per_peer.get(slot)
    return entry if isinstance(entry, dict) else None


def _write_peer_ua_session(
    peer: dict[str, Any],
    peer_id: bytes,
    slot: int,
    tgid: int,
    expires: float,
    sys_cfg: dict[str, Any],
) -> None:
    entry = {"tgid": int(tgid), "expires": float(expires)}
    pk = bytes_4(int_id(peer_id))
    sys_cfg.setdefault("_PEER_UA_SESSIONS", {}).setdefault(pk, {})[slot] = entry
    peer.setdefault("_UA_SESSION", {})[slot] = entry


def peer_single_mode(peer: dict[str, Any], sys_cfg: dict[str, Any]) -> bool:
    from adn_server.application.report.payloads import resolve_peer_single_and_timer

    single, _ = resolve_peer_single_and_timer(peer_options_fields(peer), sys_cfg)
    return single


def _peer_ua_multi_store(sys_cfg: dict[str, Any]) -> dict[bytes, dict[int, set[int]]]:
    store = sys_cfg.setdefault("_PEER_UA_MULTI_TGS", {})
    if not isinstance(store, dict):
        store = {}
        sys_cfg["_PEER_UA_MULTI_TGS"] = store
    return store


def register_peer_ua_multi_tg(
    peer: dict[str, Any],
    peer_id: bytes,
    slot: int,
    tgid: int,
    sys_cfg: dict[str, Any],
) -> None:
    """SINGLE=0: accumulate keyed dynamic TGs per peer/slot until TG 4000."""
    if peer_single_mode(peer, sys_cfg):
        return
    tgid_i = int(tgid)
    if tgid_i <= 0 or tgid_i == 4000:
        return
    if peer_receives_group_tgid(peer, slot, tgid_i):
        return
    pk = bytes_4(int_id(peer_id))
    per_peer = _peer_ua_multi_store(sys_cfg).setdefault(pk, {})
    slot_set = per_peer.setdefault(int(slot), set())
    slot_set.add(tgid_i)


def peer_owns_multi_dynamic_ua(
    peer: dict[str, Any],
    slot: int,
    tgid: int,
    sys_cfg: dict[str, Any] | None,
    *,
    peer_id: bytes | None = None,
) -> bool:
    """True when SINGLE=0 peer has keyed this non-static dynamic TG on ``slot``."""
    if not sys_cfg or peer_single_mode(peer, sys_cfg):
        return False
    if peer_id is None:
        return False
    if peer_receives_group_tgid(peer, slot, tgid):
        return False
    pk = bytes_4(int_id(peer_id))
    store = sys_cfg.get("_PEER_UA_MULTI_TGS")
    if not isinstance(store, dict):
        return False
    per_peer = store.get(pk)
    if not isinstance(per_peer, dict):
        return False
    slot_set = per_peer.get(int(slot))
    return isinstance(slot_set, set) and int(tgid) in slot_set


def register_peer_ua_session(
    peer: dict[str, Any],
    peer_id: bytes,
    slot: int,
    tgid: int,
    sys_cfg: dict[str, Any],
    *,
    now: float | None = None,
) -> None:
    """Track UA TG for this hotspot (SINGLE=1 exclusive; SINGLE=0 multi-dynamic set)."""
    if not peer_single_mode(peer, sys_cfg):
        register_peer_ua_multi_tg(peer, peer_id, slot, tgid, sys_cfg)
        return
    from adn_server.application.report.payloads import resolve_peer_single_and_timer

    _, timer_min = resolve_peer_single_and_timer(peer_options_fields(peer), sys_cfg)
    pkt_time = time.time() if now is None else now
    _write_peer_ua_session(
        peer,
        peer_id,
        slot,
        int(tgid),
        pkt_time + float(timer_min) * 60.0,
        sys_cfg,
    )


def seed_peer_ua_session_from_status(
    peer: dict[str, Any],
    peer_id: bytes,
    slot: int,
    status_slot: dict[str, Any],
    sys_cfg: dict[str, Any],
    *,
    now: float | None = None,
) -> None:
    """Seed SINGLE session after RPTO when TX happened before OPTIONS (inject-only)."""
    if not peer_single_mode(peer, sys_cfg):
        return
    pkt_time = time.time() if now is None else now
    if peer_single_exclusive_tgid(peer, slot, sys_cfg, peer_id=peer_id, now=pkt_time) is not None:
        return
    rx_peer = status_slot.get("RX_PEER", b"\x00\x00\x00\x00")
    if bytes_4(int_id(peer_id)) != bytes_4(int_id(rx_peer)):
        return
    rx_tgid = int_id(status_slot.get("RX_TGID", b"\x00\x00\x00"))
    if rx_tgid <= 0:
        return
    connected_at = float(peer.get("CONNECTED", 0) or 0)
    rx_time = float(status_slot.get("RX_TIME", 0) or 0)
    if connected_at > 0 and rx_time < connected_at - 0.5:
        return
    register_peer_ua_session(peer, peer_id, slot, rx_tgid, sys_cfg, now=pkt_time)


def clear_peer_rx_status_slots(
    status: dict[Any, Any],
    peer_id: bytes,
    *,
    slot: int | None = None,
) -> None:
    """Reset RX fields on slots last owned by this peer (avoids stale OPTIONS seed)."""
    pk = bytes_4(int_id(peer_id))
    slots = (int(slot),) if slot is not None else (1, 2)
    for slot_id in slots:
        slot_st = status.get(slot_id)
        if not isinstance(slot_st, dict):
            continue
        if bytes_4(int_id(slot_st.get("RX_PEER", b"\x00"))) != pk:
            continue
        slot_st["RX_PEER"] = b"\x00"
        slot_st["RX_TGID"] = b"\x00\x00\x00"
        slot_st["RX_STREAM_ID"] = b"\x00"
        slot_st["RX_TIME"] = 0.0


def export_peer_ua_sessions(
    sys_cfg: dict[str, Any],
    peer_id: bytes | int,
    *,
    now: float | None = None,
) -> dict[str, dict[str, float | int]]:
    """Active SINGLE sessions for monitor snapshot (server source of truth)."""
    pkt_time = time.time() if now is None else now
    pk = bytes_4(int_id(peer_id))
    out: dict[str, dict[str, float | int]] = {}
    store = sys_cfg.get("_PEER_UA_SESSIONS")
    if not isinstance(store, dict):
        return out
    per_peer = store.get(pk)
    if not isinstance(per_peer, dict):
        return out
    for slot in (1, 2):
        entry = per_peer.get(slot)
        if not isinstance(entry, dict):
            continue
        exp = float(entry.get("expires", 0) or 0)
        tgid = int(entry.get("tgid", 0) or 0)
        if tgid > 0 and exp > pkt_time:
            out[str(slot)] = {"tgid": tgid, "expires_at": exp}
    return out


def restore_peer_ua_entries_to_memory(
    sys_cfg: dict[str, Any],
    peer_id: bytes,
    entries: list[Any],
    *,
    now: float | None = None,
) -> list[int]:
    """Apply persisted dynamic TG rows to ``_PEER_UA_SESSIONS`` / ``_PEER_UA_MULTI_TGS``."""
    pkt_time = time.time() if now is None else now
    pk = bytes_4(int_id(peer_id))
    restored: list[int] = []
    for entry in entries:
        tgid = int(entry.tgid)
        slot = int(entry.slot)
        if entry.single_mode:
            expires = entry.expires_at
            if expires is not None and float(expires) <= pkt_time:
                continue
            per_peer = sys_cfg.setdefault("_PEER_UA_SESSIONS", {}).setdefault(pk, {})
            per_peer[slot] = {
                "tgid": tgid,
                "expires": float(expires) if expires is not None else 0.0,
            }
            restored.append(tgid)
        else:
            multi = sys_cfg.setdefault("_PEER_UA_MULTI_TGS", {}).setdefault(pk, {})
            multi.setdefault(slot, set()).add(tgid)
            restored.append(tgid)
    return restored


def purge_expired_peer_ua_sessions(sys_cfg: dict[str, Any], *, now: float | None = None) -> None:
    """Drop expired SINGLE=1 sessions from in-memory store."""
    pkt_time = time.time() if now is None else now
    store = sys_cfg.get("_PEER_UA_SESSIONS")
    if not isinstance(store, dict):
        return
    for pk in list(store.keys()):
        per_peer = store.get(pk)
        if not isinstance(per_peer, dict):
            continue
        for slot in list(per_peer.keys()):
            entry = per_peer.get(slot)
            if not isinstance(entry, dict):
                continue
            exp = float(entry.get("expires", 0) or 0)
            if exp > 0 and pkt_time >= exp:
                per_peer.pop(slot, None)
        if not per_peer:
            store.pop(pk, None)


def clear_peer_ua_sessions(
    peer: dict[str, Any],
    sys_cfg: dict[str, Any],
    peer_id: bytes,
    *,
    slot: int | None = None,
) -> None:
    """Clear per-peer UA state (SINGLE session and/or SINGLE=0 multi-dynamic set)."""
    pk = bytes_4(int_id(peer_id))
    store = sys_cfg.get("_PEER_UA_SESSIONS")
    if isinstance(store, dict) and pk in store:
        if slot is None:
            store.pop(pk, None)
        else:
            per_peer = store.get(pk)
            if isinstance(per_peer, dict):
                per_peer.pop(slot, None)
    multi = sys_cfg.get("_PEER_UA_MULTI_TGS")
    if isinstance(multi, dict) and pk in multi:
        if slot is None:
            multi.pop(pk, None)
        else:
            per_peer = multi.get(pk)
            if isinstance(per_peer, dict):
                per_peer.pop(int(slot), None)
    sessions = peer.get("_UA_SESSION")
    if isinstance(sessions, dict):
        if slot is None:
            sessions.clear()
        else:
            sessions.pop(slot, None)


def peer_single_exclusive_tgid(
    peer: dict[str, Any],
    slot: int,
    sys_cfg: dict[str, Any],
    *,
    peer_id: bytes | None = None,
    now: float | None = None,
) -> int | None:
    """Active SINGLE session TG on ``slot``, or ``None`` when no exclusive lock."""
    if not peer_single_mode(peer, sys_cfg):
        return None
    pkt_time = time.time() if now is None else now
    entry = _peer_ua_session_entry(sys_cfg, peer_id, slot)
    if entry is None:
        sessions = peer.get("_UA_SESSION")
        if isinstance(sessions, dict):
            entry = sessions.get(slot)
    if not isinstance(entry, dict):
        return None
    if pkt_time >= float(entry.get("expires", 0)):
        return None
    locked = entry.get("tgid")
    return int(locked) if locked is not None else None


def peer_single_blocks_group_voice(
    peer: dict[str, Any],
    slot: int,
    tgid: int,
    sys_cfg: dict[str, Any] | None,
    *,
    peer_id: bytes | None = None,
    now: float | None = None,
) -> bool:
    """True when SINGLE=1 peer must not receive downlink for ``tgid`` on ``slot``.

    With an active session on TG X, every other TG (static or dynamic) is blocked
    until the TIMER expires or a new local TX replaces the session.
    """
    if not sys_cfg:
        return False
    locked = peer_single_exclusive_tgid(peer, slot, sys_cfg, peer_id=peer_id, now=now)
    if locked is None:
        return False
    return int(tgid) != locked


def peer_receives_group_tgid(peer: dict[str, Any], slot: int, tgid: int) -> bool:
    """True when peer RPTO OPTIONS list the group TG on TS1 or TS2 (legacy REPEAT parity).

    Voice may arrive on either timeslot; hotspots in repeater mode often use one RF
    slot while self-service lists the TG on the other.
    """
    del slot
    return peer_options_static_tg_slot(peer, tgid) is not None


def peer_options_static_tg_slot(peer: dict[str, Any], tgid: int) -> int | None:
    """Timeslot (1 or 2) where peer OPTIONS list ``tgid``, when unambiguous."""
    from adn_server.application.report.payloads import parse_peer_options_static

    ts1, ts2 = parse_peer_options_static(peer.get("OPTIONS"))
    tg = str(tgid)
    in_ts1 = tg in ts1
    in_ts2 = tg in ts2
    if in_ts1 and not in_ts2:
        return 1
    if in_ts2 and not in_ts1:
        return 2
    return None


def peer_single_blocks_uplink(
    peer: dict[str, Any],
    peer_id: bytes,
    slot: int,
    tgid: int,
    sys_cfg: dict[str, Any] | None,
    *,
    now: float | None = None,
) -> bool:
    """SINGLE=1 never blocks local TX; a new TG replaces the session (see ``register_peer_ua_session``).

    Downlink exclusivity is enforced by :func:`peer_single_blocks_group_voice` only.
    """
    del peer, peer_id, slot, tgid, sys_cfg, now
    return False


def _peer_owns_dynamic_ua(
    peer: dict[str, Any],
    slot: int,
    tgid: int,
    sys_cfg: dict[str, Any] | None,
    *,
    peer_id: bytes | None = None,
    now: float | None = None,
) -> bool:
    """True when ``tgid`` is a non-static UA this peer activated (SINGLE session owner)."""
    if peer_receives_group_tgid(peer, slot, tgid):
        return False
    if not sys_cfg:
        return False
    locked = peer_single_exclusive_tgid(peer, slot, sys_cfg, peer_id=peer_id, now=now)
    return locked is not None and int(tgid) == locked


def peer_should_receive_group_voice(
    peer: dict[str, Any],
    slot: int,
    tgid: int,
    *,
    peer_id: bytes | None = None,
    system: str | None = None,
    bridges: dict[str, Any] | None = None,
    subscription_store: Any | None = None,
    connected_count: int = 1,
    sys_cfg: dict[str, Any] | None = None,
    now: float | None = None,
) -> bool:
    """Whether a hotspot should get downlink / monitor voice for ``(slot, tgid)``.

    Inject-only multi-hotspot rules (per peer):

    1. ``SINGLE=1`` with an active session on another TG → deny all other TGs.
    2. TG in this peer's OPTIONS static list (TS1 or TS2) → allow (when not blocked by SINGLE).
    3. ``SINGLE=1``: dynamic UA owned by this peer's exclusive session → allow.
    4. ``SINGLE=0``: dynamic UA this peer keyed (multi set) → allow.
    5. Sole connected hotspot with an ACTIVE bridge leg for ``(slot, tgid)`` → allow.
    6. Otherwise → deny (no fan-out).

    A system-wide ACTIVE bridge leg must **not** fan out to every hotspot when
    several peers are online; that was the regression when ``bridges`` alone
    decided fan-out for all connected hotspots.
    """
    if peer_single_blocks_group_voice(peer, slot, tgid, sys_cfg, peer_id=peer_id, now=now):
        return False
    if peer_receives_group_tgid(peer, slot, tgid):
        return True
    if _peer_owns_dynamic_ua(peer, slot, tgid, sys_cfg, peer_id=peer_id, now=now):
        return True
    if peer_owns_multi_dynamic_ua(peer, slot, tgid, sys_cfg, peer_id=peer_id):
        return True
    if connected_count == 1 and system and _system_has_active_bridge_leg(
        bridges, system, slot, tgid, subscription_store=subscription_store
    ):
        return True
    return False


def peer_matches_rf_source(peer_id: bytes, rf_src: bytes, peers: dict[Any, Any]) -> bool:
    """True when a hotspot radio id matches the voice RF source (parrot / echo downlink)."""
    peer_b = _peer_key_from_int(peer_id)
    return peer_b in _fuzzy_peer_matches(int_id(rf_src), peers)
