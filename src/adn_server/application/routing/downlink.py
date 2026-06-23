# ADN DMR Peer Server - per-hotspot downlink gate
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

"""Single authority for hotspot downlink eligibility, remap, slot busy, and hangtime."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from adn_server.domain import HBPF_DATA_SYNC, HBPF_SLT_VTERM, bytes_3, bytes_4, int_id

from .helpers import (
    SIMPLEX_VOICE_SLOT,
    hbp_slot_blocks_group_voice_for_peer,
    is_special_tg,
    master_per_peer_slot_contention,
    parse_dmrd_burst_fields,
    parse_dmrd_route_fields,
    peer_downlink_voice_slot,
    peer_is_simplex,
    peer_receives_group_tgid,
    peer_should_receive_group_voice,
    remap_dmrd_to_peer_static_slot,
    synthetic_group_dmrd_route_packet,
)

PeerVoiceSlotRow = dict[str, Any]
PeerVoiceSlotMap = dict[int, PeerVoiceSlotRow]
PeerHangMap = dict[int, tuple[int, float]]


@dataclass
class DownlinkContext:
    """Runtime state for per-hotspot downlink gating on one MASTER."""

    config: dict[str, Any]
    system_name: str
    sys_cfg: dict[str, Any]
    peers: dict[Any, Any]
    status: dict[int, dict[str, Any]]
    connected_count: int = 0
    peer_voice_slots: dict[bytes, PeerVoiceSlotMap] = field(default_factory=dict)
    peer_voice_hangtime: dict[bytes, PeerHangMap] = field(default_factory=dict)
    subscription_store: Any | None = None

    def per_peer_contention(self) -> bool:
        return master_per_peer_slot_contention(
            self.config,
            self.system_name,
            self.sys_cfg,
            connected_count=self.connected_count,
        )


def normalize_ua_voice_slot(peer: dict[str, Any], wire_slot: int) -> int:
    """SINGLE / UA dynamics use TS2 on simplex hotspots (MMDVMHost DMO parity)."""
    if peer_is_simplex(peer):
        return SIMPLEX_VOICE_SLOT
    return int(wire_slot)


def peer_listen_slots(peer: dict[str, Any], tgid: int) -> list[int]:
    """Voice slots where this peer listens for ``tgid`` (static OPTIONS or wire fallback)."""
    from adn_server.application.report.payloads import parse_peer_options_static

    if peer_is_simplex(peer):
        return [SIMPLEX_VOICE_SLOT]
    ts1, ts2 = parse_peer_options_static(peer.get("OPTIONS"))
    tg = str(tgid)
    in_ts1 = tg in ts1
    in_ts2 = tg in ts2
    if in_ts1 and in_ts2:
        return [1, 2]
    if in_ts1:
        return [1]
    if in_ts2:
        return [2]
    static = peer_options_static_tg_slot(peer, tgid)
    if static is not None:
        return [static]
    return []


def peer_options_static_tg_slot(peer: dict[str, Any], tgid: int) -> int | None:
    from adn_server.application.routing.helpers import peer_options_static_tg_slot as _slot

    return _slot(peer, tgid)


def peer_accepts_group_downlink(
    ctx: DownlinkContext,
    peer_id: bytes,
    peer: dict[str, Any],
    wire_slot: int,
    tgid: int,
    *,
    call_type: str = "group",
) -> bool:
    """P1: same eligibility as DMRD group downlink for ``(wire_slot, tgid)``."""
    if call_type not in ("group", "vcsbk"):
        return True
    return peer_should_receive_group_voice(
        peer,
        wire_slot,
        tgid,
        peer_id=peer_id,
        system=ctx.system_name,
        bridges=None,
        subscription_store=ctx.subscription_store,
        connected_count=ctx.connected_count,
        sys_cfg=ctx.sys_cfg,
    )


def peer_hangtime_voice_slots(
    peer: dict[str, Any],
    wire_slot: int,
    tgid: int,
    sys_cfg: dict[str, Any] | None,
    *,
    peer_id: bytes | None = None,
) -> set[int]:
    """RF / OPTIONS slots that share transmit hangtime for this downlink."""
    rf_slot = normalize_ua_voice_slot(peer, int(wire_slot))
    listen_slot = peer_downlink_voice_slot(
        peer, int(wire_slot), int(tgid), sys_cfg, peer_id=peer_id,
    )
    return {int(rf_slot), int(wire_slot), int(listen_slot)}


def peer_slot_blocks_downlink(
    ctx: DownlinkContext,
    peer_id: bytes,
    peer: dict[str, Any],
    packet: bytes,
    *,
    pkt_time: float | None = None,
) -> bool:
    """P2/P3: True when slot busy or GROUP_HANGTIME blocks this downlink."""
    if packet[:4] != b"DMRD":
        return False
    parsed = parse_dmrd_route_fields(packet)
    if parsed is None:
        return False
    wire_slot, tgid, call_type = parsed
    if call_type not in ("group", "vcsbk"):
        return False
    if not ctx.per_peer_contention():
        return False
    burst = parse_dmrd_burst_fields(packet)
    stream_id = burst[3] if burst is not None else b""
    hang = float(ctx.sys_cfg.get("GROUP_HANGTIME", 0) or 0)
    now = time.time() if pkt_time is None else float(pkt_time)
    pk = bytes_4(int_id(peer_id))
    peer_slots = ctx.peer_voice_slots.get(pk)
    voice_slots = peer_hangtime_voice_slots(
        peer, wire_slot, tgid, ctx.sys_cfg, peer_id=peer_id,
    )
    incoming_tgid_b = bytes_3(tgid)
    for voice_slot in sorted(voice_slots):
        hang_row = ctx.peer_voice_hangtime.get(pk, {}).get(voice_slot)
        slot_st = ctx.status.get(voice_slot, {})
        if hbp_slot_blocks_group_voice_for_peer(
            slot_st,
            peer_id,
            incoming_tgid_b,
            stream_id,
            now,
            hang,
            per_peer=True,
            peers=ctx.peers,
            peer_slots=peer_slots,
            peer_hang_row=hang_row,
            voice_slot=voice_slot,
        ):
            return True
    return False


def remap_dmrd_for_peer(
    packet: bytes,
    peer: dict[str, Any],
    sys_cfg: dict[str, Any] | None,
    *,
    peer_id: bytes | None = None,
    voice_slot: int | None = None,
) -> bytes:
    """Flip DMRD slot bit to the peer RF listen slot for this TG."""
    if voice_slot is not None:
        parsed = parse_dmrd_route_fields(packet)
        if parsed is None:
            return packet
        wire_slot, tgid, call_type = parsed
        if call_type not in ("group", "vcsbk") or is_special_tg(str(tgid)):
            return packet
        if int(voice_slot) == int(wire_slot):
            return packet
        bits = packet[15]
        new_bits = bits ^ (1 << 7)
        return packet[:15] + bytes([new_bits]) + packet[16:]
    return remap_dmrd_to_peer_static_slot(packet, peer, sys_cfg, peer_id=peer_id)


def apply_hangtime_after_vterm(
    ctx: DownlinkContext,
    peer_id: bytes,
    voice_slot: int,
    tgid: int,
    *,
    pkt_time: float | None = None,
) -> None:
    """P3: record post-VTERM GROUP_HANGTIME window for SINGLE=0 hotspots."""
    now = time.time() if pkt_time is None else float(pkt_time)
    pk = bytes_4(int_id(peer_id))
    per_slot = ctx.peer_voice_slots.get(pk, {})
    per_slot.pop(int(voice_slot), None)
    ctx.peer_voice_hangtime.setdefault(pk, {})[int(voice_slot)] = (int(tgid), float(now))


def touch_peer_voice_slot(
    ctx: DownlinkContext,
    peer_id: bytes,
    voice_slot: int,
    stream_id: bytes,
    tgid: bytes,
    *,
    pkt_time: float | None = None,
    clear_hangtime: bool = True,
) -> None:
    """Open per-hotspot voice session until VTERM."""
    now = time.time() if pkt_time is None else float(pkt_time)
    pk = bytes_4(int_id(peer_id))
    ctx.peer_voice_slots.setdefault(pk, {})[int(voice_slot)] = {
        "stream_id": stream_id,
        "tgid": int_id(tgid),
        "time": float(now),
    }
    if clear_hangtime:
        ctx.peer_voice_hangtime.get(pk, {}).pop(int(voice_slot), None)


def end_peer_voice_slot(
    ctx: DownlinkContext,
    peer_id: bytes,
    voice_slot: int,
    stream_id: bytes,
    tgid: bytes,
    *,
    pkt_time: float | None = None,
    apply_hangtime: bool = True,
) -> None:
    """Close session on VTERM; ingress VTERM may start GROUP_HANGTIME window."""
    now = time.time() if pkt_time is None else float(pkt_time)
    pk = bytes_4(int_id(peer_id))
    per_slot = ctx.peer_voice_slots.get(pk, {})
    active = per_slot.pop(int(voice_slot), None)
    if not apply_hangtime:
        return
    if isinstance(active, dict):
        ended_tg = int(active.get("tgid", 0) or 0)
    else:
        ended_tg = int_id(tgid)
    if ended_tg:
        apply_hangtime_after_vterm(ctx, peer_id, voice_slot, ended_tg, pkt_time=now)


def track_peer_group_dmrd(
    ctx: DownlinkContext,
    peer_id: bytes,
    packet: bytes,
    peer: dict[str, Any],
    *,
    pkt_time: float | None = None,
    from_ingress: bool = False,
) -> None:
    """Update per-hotspot slot state from downlink or ingress DMRD."""
    burst = parse_dmrd_burst_fields(packet)
    if burst is None:
        return
    wire_slot, frame_type, dtype_vseq, stream_id, dst_id, _call_type = burst
    voice_slot = peer_downlink_voice_slot(
        peer, wire_slot, int_id(dst_id), ctx.sys_cfg, peer_id=peer_id,
    )
    if frame_type == HBPF_DATA_SYNC and dtype_vseq == HBPF_SLT_VTERM:
        end_peer_voice_slot(
            ctx,
            peer_id,
            voice_slot,
            stream_id,
            dst_id,
            pkt_time=pkt_time,
            apply_hangtime=from_ingress,
        )
        return
    touch_peer_voice_slot(
        ctx,
        peer_id,
        voice_slot,
        stream_id,
        dst_id,
        pkt_time=pkt_time,
        clear_hangtime=from_ingress,
    )


def build_dmra_route_packet(slot: int, tgid: int, stream_id: bytes | None = None) -> bytes:
    """Synthetic DMRD for DMRA / monitor fan-out lookup."""
    return synthetic_group_dmrd_route_packet(slot, tgid, stream_id)


def peer_accepts_dmra(
    ctx: DownlinkContext,
    peer_id: bytes,
    slot: int,
    tgid: int,
) -> bool:
    """P1: DMRA uses same accept + slot-busy rules as DMRD."""
    peer = ctx.peers.get(peer_id)
    if not isinstance(peer, dict):
        return False
    route_pkt = build_dmra_route_packet(slot, tgid)
    if not peer_accepts_group_downlink(ctx, peer_id, peer, slot, tgid):
        return False
    remapped = remap_dmrd_for_peer(route_pkt, peer, ctx.sys_cfg, peer_id=peer_id)
    return not peer_slot_blocks_downlink(ctx, peer_id, peer, remapped)


def peer_would_show_group_voice_on_monitor(
    ctx: DownlinkContext | None,
    peer_id: bytes,
    peer: dict[str, Any],
    wire_slot: int,
    tgid: int,
    *,
    options_eligible: bool,
    stream_id: bytes | None = None,
) -> bool:
    """Monitor fan-out: OPTIONS plus the same slot/hangtime gate as ``send_peer``.

    ``stream_id`` must match the BRDG_EVENT stream (field 4) so bridge ``TX_STREAM_ID``
    exemption aligns with live DMRD delivery — zero stream id false-blocks after hangtime.
    """
    if not options_eligible:
        return False
    if ctx is None or not ctx.per_peer_contention():
        return True
    route_pkt = build_dmra_route_packet(wire_slot, tgid, stream_id)
    remapped = remap_dmrd_for_peer(route_pkt, peer, ctx.sys_cfg, peer_id=peer_id)
    return not peer_slot_blocks_downlink(ctx, peer_id, peer, remapped)


def iter_downlink_voice_slots(
    peer: dict[str, Any],
    wire_slot: int,
    tgid: int,
) -> list[int]:
    """P4: slots to deliver when static TG spans TS1+TS2."""
    listen = peer_listen_slots(peer, tgid)
    if listen:
        return listen
    if peer_receives_group_tgid(peer, wire_slot, tgid):
        return [peer_downlink_voice_slot(peer, wire_slot, tgid)]
    return [wire_slot]
