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
from ...domain.hbp_protocol import HBPF_SLT_VTERM, STREAM_TO

PeerVoiceSlotRow = dict[str, Any]
PeerVoiceSlotMap = dict[int, PeerVoiceSlotRow]

RF_MODE_SIMPLEX = "simplex"
RF_MODE_DUPLEX = "duplex"
# MMDVMHost DMO: downlink DMRD with TS1 bit set is dropped; only TS2 passes (DMRNetwork.cpp).
SIMPLEX_VOICE_SLOT = 2


def _peer_freq_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip("\x00").strip()
    return str(value or "").strip()


def parse_peer_slots_code(slots: Any) -> int | None:
    """MMDVM RPTC ``SLOTS`` byte: 4=simplex, 1–3=duplex (per MMDVMHost / Wireshark dissector)."""
    if isinstance(slots, bytes):
        raw = slots[:1]
    elif slots is None:
        return None
    else:
        text = str(slots).strip()
        raw = text[:1].encode("ascii", errors="ignore") if text else b""
    if not raw:
        return None
    try:
        return int(raw.decode("ascii", errors="ignore"))
    except ValueError:
        return None


def derive_peer_rf_mode(peer: dict[str, Any]) -> str:
    """Classify hotspot RF from RPTC ``SLOTS`` and matching RX/TX frequencies."""
    slots_i = parse_peer_slots_code(peer.get("SLOTS"))
    if slots_i == 4:
        return RF_MODE_SIMPLEX
    rx = _peer_freq_text(peer.get("RX_FREQ"))
    tx = _peer_freq_text(peer.get("TX_FREQ"))
    if rx and tx and rx == tx:
        return RF_MODE_SIMPLEX
    return RF_MODE_DUPLEX


def apply_peer_rf_mode(peer: dict[str, Any]) -> str:
    """Store derived ``RF_MODE`` on the peer after RPTC (or test harness setup)."""
    mode = derive_peer_rf_mode(peer)
    peer["RF_MODE"] = mode
    return mode


def peer_rf_mode(peer: dict[str, Any]) -> str:
    """Cached or derived simplex/duplex mode for downlink and monitor."""
    cached = peer.get("RF_MODE")
    if cached in (RF_MODE_SIMPLEX, RF_MODE_DUPLEX):
        return str(cached)
    return derive_peer_rf_mode(peer)


def peer_is_simplex(peer: dict[str, Any]) -> bool:
    return peer_rf_mode(peer) == RF_MODE_SIMPLEX


def slot_has_active_voice(slot_st: dict[str, Any], pkt_time: float) -> bool:
    """True when the slot has an active group-voice RX or TX leg (within STREAM_TO)."""
    rx_type = slot_st.get("RX_TYPE")
    if rx_type is not None and rx_type != HBPF_SLT_VTERM:
        if (pkt_time - float(slot_st.get("RX_TIME", 0))) < STREAM_TO:
            return True
    tx_type = slot_st.get("TX_TYPE")
    if tx_type is not None and tx_type != HBPF_SLT_VTERM:
        if (pkt_time - float(slot_st.get("TX_TIME", 0))) < STREAM_TO:
            return True
    return False


def _slot_last_voice_activity(slot_st: dict[str, Any]) -> tuple[bytes, float]:
    """Most recent RX/TX TG and timestamp on this slot."""
    rx_tg = slot_st.get("RX_TGID", b"\x00\x00\x00")
    rx_t = float(slot_st.get("RX_TIME", 0))
    tx_tg = slot_st.get("TX_TGID", b"\x00\x00\x00")
    tx_t = float(slot_st.get("TX_TIME", 0))
    if tx_t >= rx_t:
        return tx_tg, tx_t
    return rx_tg, rx_t


def slot_in_group_hangtime(
    slot_st: dict[str, Any],
    incoming_tgid_b: bytes,
    pkt_time: float,
    group_hangtime: float,
) -> bool:
    """True when the slot is idle but other TGs are blocked for GROUP_HANGTIME seconds."""
    hang = float(group_hangtime or 0)
    if hang <= 0:
        return False
    if slot_has_active_voice(slot_st, pkt_time):
        return False
    last_tg, last_t = _slot_last_voice_activity(slot_st)
    if last_t <= 0:
        return False
    if bytes_4(int_id(incoming_tgid_b)) == bytes_4(int_id(last_tg)):
        return False
    return (pkt_time - last_t) < hang


def hbp_slot_blocks_group_voice(
    slot_st: dict[str, Any],
    incoming_tgid_b: bytes,
    stream_id: bytes,
    pkt_time: float,
    group_hangtime: float,
    *,
    allow_same_stream: bool = True,
) -> bool:
    """True when group voice must not be routed or repeated to this slot.

    Active QSO: any other stream is blocked (independent of GROUP_HANGTIME).
    Post-VTERM: other TGs are blocked for ``group_hangtime`` seconds from config.
    """
    if allow_same_stream and stream_id:
        if stream_id == slot_st.get("RX_STREAM_ID") or stream_id == slot_st.get("TX_STREAM_ID"):
            return False
    if slot_has_active_voice(slot_st, pkt_time):
        return True
    return slot_in_group_hangtime(slot_st, incoming_tgid_b, pkt_time, group_hangtime)


def slot_status_peer_owner(slot_st: dict[str, Any]) -> bytes | None:
    """Hotspot radio id that last owned this slot STATUS row (RX preferred, then TX)."""
    rx = slot_st.get("RX_PEER")
    if rx is not None and int_id(rx) != 0:
        return bytes_4(int_id(rx))
    tx = slot_st.get("TX_PEER")
    if tx is not None and int_id(tx) != 0:
        return bytes_4(int_id(tx))
    return None


def peer_key_in_peers(peer_id: bytes, peers: dict[Any, Any] | None) -> bool:
    """True when ``peer_id`` is a connected hotspot key in ``PEERS``."""
    if not peers:
        return False
    pk = bytes_4(int_id(peer_id))
    if pk in peers:
        return True
    for key in peers:
        try:
            if bytes_4(int_id(key)) == pk:
                return True
        except (TypeError, ValueError):
            continue
    return False


def slot_status_hotspot_owner(
    slot_st: dict[str, Any],
    peers: dict[Any, Any] | None = None,
) -> bytes | None:
    """Connected hotspot owning this slot row; ignores bridge ``TX_PEER`` (e.g. OBP 73010)."""
    for field in ("RX_PEER", "TX_PEER"):
        raw = slot_st.get(field)
        if raw is None or int_id(raw) == 0:
            continue
        pk = bytes_4(int_id(raw))
        if peers is not None and not peer_key_in_peers(pk, peers):
            continue
        return pk
    return None


def _peer_transmit_hangtime_blocks(
    hang_row: tuple[int, float] | None,
    incoming_tgid_b: bytes,
    pkt_time: float,
    group_hangtime: float,
) -> bool:
    """True when hotspot RF transmit hangtime blocks a different TG."""
    hang = float(group_hangtime or 0)
    if hang <= 0 or hang_row is None:
        return False
    last_tg, last_t = hang_row
    return int_id(incoming_tgid_b) != int(last_tg) and (pkt_time - float(last_t)) < hang


def _peer_status_rx_hangtime_blocks(
    peer_id: bytes,
    slot_st: dict[str, Any],
    incoming_tgid_b: bytes,
    pkt_time: float,
    group_hangtime: float,
) -> bool:
    """Ingress RX hangtime for this hotspot (ignores bridge TX_TGID on shared STATUS)."""
    pk = bytes_4(int_id(peer_id))
    if bytes_4(int_id(slot_st.get("RX_PEER", b""))) != pk:
        return False
    if slot_has_active_voice(slot_st, pkt_time):
        return False
    rx_tg = slot_st.get("RX_TGID", b"\x00\x00\x00")
    rx_t = float(slot_st.get("RX_TIME", 0))
    hang = float(group_hangtime or 0)
    if hang <= 0 or rx_t <= 0:
        return False
    if int_id(incoming_tgid_b) == int_id(rx_tg):
        return False
    return (pkt_time - rx_t) < hang


def peer_hotspot_voice_slot_busy(
    peer_id: bytes,
    voice_slot: int,
    stream_id: bytes,
    incoming_tgid_b: bytes,
    slot_st: dict[str, Any],
    peer_slots: PeerVoiceSlotMap | None,
    hang_row: tuple[int, float] | None,
    pkt_time: float,
    group_hangtime: float,
    *,
    peers: dict[Any, Any] | None = None,
) -> bool:
    """True when this hotspot must not receive another group stream on ``voice_slot``."""
    pk = bytes_4(int_id(peer_id))
    # Ingress-owned post-VTERM window: must win over OBP bridge TX stamp on STATUS[slot].
    if _peer_transmit_hangtime_blocks(hang_row, incoming_tgid_b, pkt_time, group_hangtime):
        return True
    # OBP bridge TX stamp on shared STATUS[slot] overrides stale per-peer session rows.
    if stream_id and stream_id == slot_st.get("TX_STREAM_ID"):
        tx_peer = slot_st.get("TX_PEER")
        if tx_peer is not None and int_id(tx_peer) != 0:
            if peers is None or not peer_key_in_peers(tx_peer, peers):
                return False
    active = (peer_slots or {}).get(int(voice_slot))
    if isinstance(active, dict):
        active_stream = active.get("stream_id")
        if stream_id and active_stream == stream_id:
            return False
        # Session stays open until VTERM clears ``peer_slots``; DMR voice has
        # inter-burst gaps longer than STREAM_TO so time-since-last-packet must
        # not release the slot to another TG mid-QSO.
        return True
    if bytes_4(int_id(slot_st.get("RX_PEER", b""))) == pk:
        if slot_has_active_voice(slot_st, pkt_time) and stream_id != slot_st.get("RX_STREAM_ID"):
            return True
        if _peer_status_rx_hangtime_blocks(
            peer_id, slot_st, incoming_tgid_b, pkt_time, group_hangtime,
        ):
            return True
    return False


def master_per_peer_slot_contention(
    config: dict[str, Any],
    system_name: str,
    system_cfg: dict[str, Any],
    *,
    connected_count: int = 0,
) -> bool:
    """True when slot busy/hangtime applies per hotspot, not globally on the MASTER row."""
    if system_cfg.get("MODE") != "MASTER":
        return False
    from ..proxy.deployment import is_proxy_inject_only

    if is_proxy_inject_only(config, system_name):
        return True
    return connected_count > 1


def inject_only_defer_obp_hbp_slot_contention(
    config: dict[str, Any],
    target_system: str,
    target_system_cfg: dict[str, Any],
    *,
    source_is_obp: bool,
    connected_count: int = 0,
) -> bool:
    """Whether OBP→MASTER ``to_target`` should skip global slot STATUS contention.

    Defer to ``send_peer`` (same as REPEAT): per-peer ``hbp_slot_blocks_group_voice_for_peer``
    + OPTIONS/UA slot remap. Global STATUS on the bridge wire TS would block cross-slot
    downlink while another peer is active on that TS even though recipients listen elsewhere.
    """
    if not source_is_obp:
        return False
    if target_system_cfg.get("MODE") != "MASTER":
        return False
    return master_per_peer_slot_contention(
        config, target_system, target_system_cfg, connected_count=connected_count,
    )


def _downlink_same_stream_for_peer(
    slot_st: dict[str, Any],
    peer_id: bytes,
    stream_id: bytes,
) -> bool:
    """True when ``stream_id`` continues an RF leg owned by ``peer_id`` (downlink fan-out)."""
    if not stream_id:
        return False
    pid = bytes_4(int_id(peer_id))
    if stream_id == slot_st.get("RX_STREAM_ID"):
        rx_peer = slot_st.get("RX_PEER")
        if rx_peer is not None and bytes_4(int_id(rx_peer)) == pid:
            return True
    if stream_id == slot_st.get("TX_STREAM_ID"):
        tx_peer = slot_st.get("TX_PEER")
        if tx_peer is not None and bytes_4(int_id(tx_peer)) == pid:
            return True
    return False


def hbp_slot_blocks_group_voice_for_peer(
    slot_st: dict[str, Any],
    peer_id: bytes,
    incoming_tgid_b: bytes,
    stream_id: bytes,
    pkt_time: float,
    group_hangtime: float,
    *,
    per_peer: bool,
    peers: dict[Any, Any] | None = None,
    peer_slots: PeerVoiceSlotMap | None = None,
    peer_hang_row: tuple[int, float] | None = None,
    voice_slot: int | None = None,
) -> bool:
    """Slot contention scoped to one hotspot when ``per_peer`` (inject-only multi-HS).

    ``STATUS[slot]`` is shared at the MASTER, but each connected hotspot has an
    independent RF timeslot. Another peer's active QSO must not block this peer.

    Inject-only OBP→HBP defers global contention and stamps bridge ``TX_*`` on the
    shared slot row before ``send_peer``. Same-stream exemption must not treat that
    bridge TX stamp as the hotspot's own leg while the peer is still on the air (RX).
    """
    if per_peer:
        if voice_slot is None:
            return False
        return peer_hotspot_voice_slot_busy(
            peer_id,
            int(voice_slot),
            stream_id,
            incoming_tgid_b,
            slot_st,
            peer_slots,
            peer_hang_row,
            pkt_time,
            group_hangtime,
            peers=peers,
        )
    return hbp_slot_blocks_group_voice(
        slot_st, incoming_tgid_b, stream_id, pkt_time, group_hangtime,
    )


def hbp_ingress_new_stream_collision(
    slot_st: dict[str, Any],
    peer_id: bytes,
    rf_src: bytes,
    stream_id: bytes,
    pkt_time: float,
    *,
    per_peer: bool,
) -> bool:
    """True when a new group-voice stream must drop on ingress (legacy routerHBP).

    Legacy blocks only when the prior stream is still open (STREAM_TO), the RF
    source differs (another subscriber), and — in inject-only — the slot row
    belongs to this hotspot. Same-subscriber rekey with a new stream id is allowed.
    """
    from ...domain.hbp_protocol import HBPF_SLT_VTERM, STREAM_TO

    if stream_id and stream_id == slot_st.get("RX_STREAM_ID"):
        return False
    if slot_st.get("RX_TYPE") == HBPF_SLT_VTERM:
        return False
    rx_time = float(slot_st.get("RX_TIME", 0) or 0)
    if pkt_time >= rx_time + STREAM_TO:
        return False
    prev_rfs = slot_st.get("RX_RFS", b"\x00\x00\x00")
    if int_id(rf_src) != 0 and bytes_4(int_id(rf_src)) == bytes_4(int_id(prev_rfs)):
        return False
    if per_peer:
        owner = slot_status_peer_owner(slot_st)
        if owner is not None and bytes_4(int_id(owner)) != bytes_4(int_id(peer_id)):
            return False
    return True


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


def is_ua_session_tgid(tgid: int) -> bool:
    """True when a keyed TG may be stored as a user-activated dynamic session.

    Excludes TG 4000 (reset command) and service/echo 9990–9999 (no SINGLE lock).
    """
    t = int(tgid)
    if t <= 0 or t == 4000:
        return False
    return not is_special_tg(str(t))


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
    burst = parse_dmrd_burst_fields(packet)
    if burst is None:
        return None
    slot, _, _, _, dst_id, call_type = burst
    return slot, int_id(dst_id), call_type


def parse_dmrd_burst_fields(
    packet: bytes,
) -> tuple[int, int, int, bytes, bytes, str] | None:
    """Parse wire slot, frame type, dtype, stream id, dst, call type from group DMRD."""
    if len(packet) < 20 or packet[:4] != b"DMRD":
        return None
    bits = packet[15]
    slot = 2 if (bits & 0x80) else 1
    if bits & 0x40:
        return None
    if (bits & 0x23) == 0x23:
        call_type = "vcsbk"
    else:
        call_type = "group"
    frame_type = (bits & 0x30) >> 4
    dtype_vseq = bits & 0xF
    return slot, frame_type, dtype_vseq, packet[16:20], packet[8:11], call_type


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
    if not is_ua_session_tgid(tgid_i):
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
    """True when SINGLE=0 peer has keyed this non-static dynamic TG (either slot)."""
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
    tgid_i = int(tgid)
    for voice_slot in (1, 2):
        slot_set = per_peer.get(voice_slot)
        if isinstance(slot_set, set) and tgid_i in slot_set:
            return True
    return False


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
    if not is_ua_session_tgid(tgid):
        return
    if not peer_single_mode(peer, sys_cfg):
        register_peer_ua_multi_tg(peer, peer_id, slot, tgid, sys_cfg)
        return
    from adn_server.application.report.payloads import resolve_peer_single_and_timer
    from adn_server.domain.ua_timer import UA_SESSION_NEVER_EXPIRES_AT, ua_timer_is_infinite

    _, timer_min = resolve_peer_single_and_timer(peer_options_fields(peer), sys_cfg)
    pkt_time = time.time() if now is None else now
    if ua_timer_is_infinite(timer_min):
        expires_at = UA_SESSION_NEVER_EXPIRES_AT
    else:
        expires_at = pkt_time + float(timer_min) * 60.0
    # One exclusive dynamic TG per hotspot (either RF slot); new local TX replaces all others.
    other_slot = 2 if int(slot) == 1 else 1
    clear_peer_ua_sessions(peer, sys_cfg, peer_id, slot=other_slot)
    _write_peer_ua_session(
        peer,
        peer_id,
        slot,
        int(tgid),
        expires_at,
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
    if not is_ua_session_tgid(rx_tgid):
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
        if is_ua_session_tgid(tgid) and (exp == 0.0 or exp > pkt_time):
            row: dict[str, float | int] = {"tgid": tgid}
            if exp > pkt_time:
                row["expires_at"] = exp
            out[str(slot)] = row
    return out


def export_peer_ua_multi_tgs(
    sys_cfg: dict[str, Any],
    peer_id: bytes | int,
) -> dict[str, list[int]]:
    """Active SINGLE=0 multi-dynamic TG sets for monitor snapshot."""
    pk = bytes_4(int_id(peer_id))
    store = sys_cfg.get("_PEER_UA_MULTI_TGS")
    if not isinstance(store, dict):
        return {}
    per_peer = store.get(pk)
    if not isinstance(per_peer, dict):
        return {}
    out: dict[str, list[int]] = {}
    for slot in (1, 2):
        tg_set = per_peer.get(slot)
        if isinstance(tg_set, set) and tg_set:
            tgids = sorted(
                int(t) for t in tg_set if is_ua_session_tgid(int(t))
            )
            if tgids:
                out[str(slot)] = tgids
    return out


def sync_peer_ua_memory_from_store(
    peer: dict[str, Any],
    peer_id: bytes,
    sys_cfg: dict[str, Any],
) -> None:
    """Copy persisted UA rows from ``sys_cfg`` onto the live peer dict after DB restore."""
    pk = bytes_4(int_id(peer_id))
    store = sys_cfg.get("_PEER_UA_SESSIONS")
    if isinstance(store, dict):
        per_peer = store.get(pk)
        if isinstance(per_peer, dict) and per_peer:
            ua = peer.setdefault("_UA_SESSION", {})
            ua.clear()
            for slot, entry in per_peer.items():
                if isinstance(entry, dict):
                    ua[slot] = dict(entry)


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
        if not is_ua_session_tgid(tgid):
            continue
        slot = int(entry.slot)
        if entry.single_mode:
            from adn_server.domain.ua_timer import UA_SESSION_NEVER_EXPIRES_AT, ua_session_never_expires

            expires = entry.expires_at
            if (
                expires is not None
                and not ua_session_never_expires(float(expires))
                and float(expires) <= pkt_time
            ):
                continue
            per_peer = sys_cfg.setdefault("_PEER_UA_SESSIONS", {}).setdefault(pk, {})
            if expires is None or ua_session_never_expires(float(expires)):
                exp_mem = UA_SESSION_NEVER_EXPIRES_AT
            else:
                exp_mem = float(expires)
            per_peer[slot] = {
                "tgid": tgid,
                "expires": exp_mem,
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
    exp = float(entry.get("expires", 0) or 0)
    if exp > 0 and pkt_time >= exp:
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
    """True when SINGLE=1 peer must not receive downlink for ``tgid``.

    With an active session on TG X, every other TG (static or dynamic) is blocked
    until the TIMER expires or a new local TX replaces the session.
    """
    del slot
    if not sys_cfg:
        return False
    for voice_slot in (1, 2):
        locked = peer_single_exclusive_tgid(
            peer, voice_slot, sys_cfg, peer_id=peer_id, now=now,
        )
        if locked is not None and int(tgid) != locked:
            return True
    return False


def peer_receives_group_tgid(peer: dict[str, Any], slot: int, tgid: int) -> bool:
    """True when peer RPTO OPTIONS list the group TG on TS1 or TS2 (legacy REPEAT parity).

    Voice may arrive on either timeslot; hotspots in repeater mode often use one RF
    slot while self-service lists the TG on the other.
    """
    del slot
    from adn_server.application.report.payloads import parse_peer_options_static

    ts1, ts2 = parse_peer_options_static(peer.get("OPTIONS"))
    tg = str(tgid)
    return tg in ts1 or tg in ts2


def peer_options_static_tg_slot(peer: dict[str, Any], tgid: int) -> int | None:
    """Timeslot (1 or 2) where peer OPTIONS list ``tgid``, when unambiguous."""
    from adn_server.application.report.payloads import parse_peer_options_static

    ts1, ts2 = parse_peer_options_static(peer.get("OPTIONS"))
    tg = str(tgid)
    in_ts1 = tg in ts1
    in_ts2 = tg in ts2
    if peer_is_simplex(peer) and (in_ts1 or in_ts2):
        return SIMPLEX_VOICE_SLOT
    if in_ts1 and not in_ts2:
        return 1
    if in_ts2 and not in_ts1:
        return 2
    return None


def synthetic_group_dmrd_route_packet(
    slot: int,
    tgid: int,
    stream_id: bytes | None = None,
) -> bytes:
    """Minimal DMRD for downlink/monitor gate lookup (slot, TG, optional stream)."""
    bits = 0x80 if int(slot) == 2 else 0
    sid = bytes_4(int_id(stream_id)) if stream_id else b"\x00" * 4
    return b"DMRD" + b"\x00" * 4 + bytes_3(tgid) + b"\x00" * 4 + bytes([bits]) + sid + b"\x00" * 34


def peer_downlink_voice_slot(
    peer: dict[str, Any],
    wire_slot: int,
    tgid: int,
    sys_cfg: dict[str, Any] | None = None,
    *,
    peer_id: bytes | None = None,
) -> int:
    """Monitor/BRDG field 7: TS where this peer listens for ``tgid`` (OPTIONS or UA)."""
    if peer_is_simplex(peer):
        return SIMPLEX_VOICE_SLOT
    static = peer_options_static_tg_slot(peer, tgid)
    if static is not None:
        return static
    if sys_cfg is not None and peer_id is not None:
        tgid_i = int(tgid)
        pk = bytes_4(int_id(peer_id))
        for voice_slot in (1, 2):
            locked = peer_single_exclusive_tgid(
                peer, voice_slot, sys_cfg, peer_id=peer_id,
            )
            if locked is not None and int(locked) == tgid_i:
                return voice_slot
        store = sys_cfg.get("_PEER_UA_MULTI_TGS")
        if isinstance(store, dict):
            per_peer = store.get(pk)
            if isinstance(per_peer, dict):
                for voice_slot in (1, 2):
                    slot_set = per_peer.get(voice_slot)
                    if isinstance(slot_set, set) and tgid_i in slot_set:
                        return voice_slot
    return int(wire_slot)


def remap_dmrd_to_peer_static_slot(
    packet: bytes,
    peer: dict[str, Any],
    sys_cfg: dict[str, Any] | None = None,
    *,
    peer_id: bytes | None = None,
) -> bytes:
    """Flip DMRD slot bit so the hotspot RF TS matches OPTIONS/UA for this TG."""
    parsed = parse_dmrd_route_fields(packet)
    if parsed is None:
        return packet
    voice_slot, tgid, call_type = parsed
    if call_type not in ("group", "vcsbk"):
        return packet
    if is_special_tg(str(tgid)):
        return packet
    cfg_slot = peer_downlink_voice_slot(
        peer, voice_slot, tgid, sys_cfg, peer_id=peer_id,
    )
    if cfg_slot == voice_slot:
        return packet
    bits = packet[15]
    new_bits = bits ^ (1 << 7)
    return packet[:15] + bytes([new_bits]) + packet[16:]


def repeat_downlink_report_slot(
    wire_slot: int,
    tgid: int,
    peers: dict[Any, Any],
    downlink_peer_ids: tuple[bytes, ...],
    sys_cfg: dict[str, Any] | None,
) -> int:
    """Monitor timeslot for REPEAT downlink START/TX (OBP bridge uses target TS, not wire slot).

    When every downlink peer maps the TG to the same OPTIONS or UA slot, use that slot so
    CTABLE chips match RF (cross-slot static/dynamic). Otherwise fall back to wire slot.
    """
    display_slots: set[int] = set()
    tgid_i = int(tgid)
    for peer_id in downlink_peer_ids:
        peer = peers.get(peer_id)
        if not isinstance(peer, dict):
            continue
        display_slots.add(
            peer_downlink_voice_slot(
                peer, wire_slot, tgid_i, sys_cfg, peer_id=peer_id,
            )
        )
    if len(display_slots) == 1:
        return display_slots.pop()
    return int(wire_slot)


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
    tgid_i = int(tgid)
    for voice_slot in (1, 2):
        locked = peer_single_exclusive_tgid(
            peer, voice_slot, sys_cfg, peer_id=peer_id, now=now,
        )
        if locked is not None and tgid_i == locked:
            return True
    return False


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
