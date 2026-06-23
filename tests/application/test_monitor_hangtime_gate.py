# ADN DMR Peer Server - monitor gate parity with send_peer after GROUP_HANGTIME
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

"""Monitor fan-out must use BRDG stream id — same gate as send_peer for new QSOs."""

from __future__ import annotations

import time

from adn_server.application.report.monitor_topology import remap_inject_proxy_voice_events
from adn_server.application.routing.downlink import (
    DownlinkContext,
    apply_hangtime_after_vterm,
    peer_slot_blocks_downlink,
)
from adn_server.domain import HBPF_DATA_SYNC, HBPF_SLT_VHEAD, HBPF_SLT_VTERM, bytes_3, bytes_4


def _peer(*, options: bytes) -> dict:
    return {
        "CONNECTION": "YES",
        "CONNECTED": 1_700_000_000,
        "IP": "203.0.113.10",
        "PORT": 62031,
        "CALLSIGN": b"CE5RPY  ",
        "OPTIONS": options,
    }


def _empty_slot() -> dict:
    return {
        "RX_TIME": 0.0,
        "TX_TIME": 0.0,
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": b"\x00\x00\x00",
        "TX_TGID": b"\x00\x00\x00",
        "RX_STREAM_ID": b"",
        "TX_STREAM_ID": b"",
        "RX_PEER": b"\x00\x00\x00\x00",
        "TX_PEER": b"\x00\x00\x00\x00",
    }


def _vhead(slot: int, tgid: int, stream: int) -> bytes:
    bits = 0x80 if slot == 2 else 0
    bits |= HBPF_DATA_SYNC << 4
    bits |= HBPF_SLT_VHEAD
    return b"".join([
        b"DMRD",
        b"\x00",
        bytes_3(100),
        bytes_3(tgid),
        bytes_4(7300392),
        bytes([bits]),
        bytes_4(stream),
    ] + [b"\x00"] * 33)


def _ctx(*, hangtime: float = 10.0) -> DownlinkContext:
    peer_hs_a = bytes_4(730039101)
    peer_hs_b = bytes_4(730039210)
    peers = {
        peer_hs_a: _peer(options=b"TS2=730,7305;SINGLE=0;"),
        peer_hs_b: _peer(options=b"TS2=7305;"),
    }
    sys_cfg = {"GROUP_HANGTIME": hangtime, "MODE": "MASTER", "MAX_PEERS": 8}
    config = {"PROXY": {"TARGET_SYSTEM": "SYSTEM"}, "SYSTEMS": {"SYSTEM": sys_cfg}}
    sys_cfg["PEERS"] = peers
    return DownlinkContext(
        config=config,
        system_name="SYSTEM",
        sys_cfg=sys_cfg,
        peers=peers,
        status={1: _empty_slot(), 2: _empty_slot()},
        connected_count=2,
    )


def test_monitor_blocks_during_hangtime_allows_new_qso_with_stream_id() -> None:
    """New QSO after GROUP_HANGTIME: monitor fan-out matches send_peer when stream id is set."""
    ctx = _ctx()
    peer_hs_a = bytes_4(730039101)
    peer_hs_b = bytes_4(730039210)
    peer = ctx.peers[peer_hs_a]
    now = time.time()
    apply_hangtime_after_vterm(ctx, peer_hs_a, 2, 7306, pkt_time=now - 1)

    new_stream = bytes_4(0xAABBCCDD)
    ctx.status[2]["TX_STREAM_ID"] = new_stream
    ctx.status[2]["TX_PEER"] = peer_hs_b
    ctx.status[2]["TX_RFS"] = bytes_4(7300392)

    burst = _vhead(2, 7305, 0xAABBCCDD)
    assert peer_slot_blocks_downlink(ctx, peer_hs_a, peer, burst)

    config = ctx.config
    peer_slots = {peer_hs_a: 7, peer_hs_b: 8}
    raw = "GROUP VOICE,START,TX,SYSTEM,{},73010,7300392,2,7305".format(
        int.from_bytes(new_stream, "big"),
    )
    during = remap_inject_proxy_voice_events(
        raw, config, config["SYSTEMS"], peer_slots, downlink_ctx=ctx,
    )
    assert {ev.split(",")[3] for ev in during} == {"SYSTEM-8"}

    ctx.peer_voice_hangtime[peer_hs_a].pop(2, None)
    assert not peer_slot_blocks_downlink(ctx, peer_hs_a, peer, burst)

    after = remap_inject_proxy_voice_events(
        raw, config, config["SYSTEMS"], peer_slots, downlink_ctx=ctx,
    )
    assert {ev.split(",")[3] for ev in after} == {"SYSTEM-7", "SYSTEM-8"}
