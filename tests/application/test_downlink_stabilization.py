# ADN DMR Peer Server - downlink stabilization (trial/downlink-clean)
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

"""P3 hangtime, P4 dual-slot, HP3ICC-style slot contention via downlink.py."""

from __future__ import annotations

from adn_server.application.routing.downlink import (
    DownlinkContext,
    iter_downlink_voice_slots,
    peer_listen_slots,
    peer_slot_blocks_downlink,
    synthetic_group_dmrd_route_packet,
    touch_peer_voice_slot,
)
from adn_server.domain import HBPF_DATA_SYNC, HBPF_SLT_VHEAD, HBPF_SLT_VTERM, bytes_3, bytes_4


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


def _ctx(*, hangtime: float = 3.0) -> DownlinkContext:
    sys_cfg = {"GROUP_HANGTIME": hangtime, "MODE": "MASTER", "MAX_PEERS": 8}
    config = {"GLOBAL": {}, "SYSTEMS": {"MASTER-A": sys_cfg}}
    return DownlinkContext(
        config=config,
        system_name="MASTER-A",
        sys_cfg=sys_cfg,
        peers={},
        status={1: _empty_slot(), 2: _empty_slot()},
        connected_count=2,
    )


def _vhead(slot: int, tgid: int, stream: int) -> bytes:
    bits = 0x80 if slot == 2 else 0
    bits |= HBPF_DATA_SYNC << 4
    bits |= HBPF_SLT_VHEAD
    return b"".join([
        b"DMRD",
        b"\x00",
        bytes_3(100),
        bytes_3(tgid),
        b"\x00\x00\x00\x00",
        bytes([bits]),
        bytes_4(stream),
    ] + [b"\x00"] * 33)


def _vterm(slot: int, tgid: int, stream: int) -> bytes:
    bits = 0x80 if slot == 2 else 0
    bits |= HBPF_DATA_SYNC << 4
    bits |= HBPF_SLT_VTERM
    return b"".join([
        b"DMRD",
        b"\x00",
        bytes_3(100),
        bytes_3(tgid),
        b"\x00\x00\x00\x00",
        bytes([bits]),
        bytes_4(stream),
    ] + [b"\x00"] * 33)


def test_single0_hangtime_blocks_other_tg() -> None:
    """P3: after VTERM, GROUP_HANGTIME blocks a different TG on the same slot."""
    ctx = _ctx(hangtime=5.0)
    peer_id = bytes_4(730002301)
    peer = {"OPTIONS": b"TS2=7141;SINGLE=0;"}
    ctx.peers[peer_id] = peer
    now = 1_000_000.0
    touch_peer_voice_slot(ctx, peer_id, 2, bytes_4(0x1111), bytes_3(7141), pkt_time=now)
    from adn_server.application.routing.downlink import end_peer_voice_slot

    end_peer_voice_slot(ctx, peer_id, 2, bytes_4(0x1111), bytes_3(7141), pkt_time=now + 1)
    blocked_pkt = synthetic_group_dmrd_route_packet(2, 71442)
    blocked_pkt = _vhead(2, 71442, 0x2222)
    assert peer_slot_blocks_downlink(ctx, peer_id, peer, blocked_pkt, pkt_time=now + 3)
    same_pkt = _vhead(2, 7141, 0x3333)
    assert not peer_slot_blocks_downlink(ctx, peer_id, peer, same_pkt, pkt_time=now + 3)


def test_hangtime_blocks_when_ua_slot_differs_from_rf_slot() -> None:
    """Hangtime on RF slot 2 must block downlink even if UA store lists TG on slot 1."""
    sys_cfg = {"GROUP_HANGTIME": 10.0, "MODE": "MASTER", "MAX_PEERS": 8}
    config = {"PROXY": {"TARGET_SYSTEM": "MASTER-A"}, "SYSTEMS": {"MASTER-A": sys_cfg}}
    peer_id = bytes_4(730039101)
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    sys_cfg["_PEER_UA_MULTI_TGS"] = {peer_id: {1: {7306}}}
    ctx = DownlinkContext(
        config=config,
        system_name="MASTER-A",
        sys_cfg=sys_cfg,
        peers={peer_id: peer},
        status={1: _empty_slot(), 2: _empty_slot()},
        connected_count=2,
    )
    now = 4_000_000.0
    touch_peer_voice_slot(ctx, peer_id, 2, bytes_4(0x1111), bytes_3(7306), pkt_time=now)
    from adn_server.application.routing.downlink import end_peer_voice_slot

    end_peer_voice_slot(ctx, peer_id, 2, bytes_4(0x1111), bytes_3(7306), pkt_time=now + 1)
    assert ctx.peer_voice_hangtime[peer_id][2] == (7306, now + 1)
    foreign = _vhead(2, 7305, 0x2222)
    assert peer_slot_blocks_downlink(ctx, peer_id, peer, foreign, pkt_time=now + 3)


def test_inject_only_hangtime_blocks_static_tg_after_dynamic_tx() -> None:
    """7306 TX then OBP/static 7305 downlink blocked for GROUP_HANGTIME (inject-only lab)."""
    sys_cfg = {"GROUP_HANGTIME": 10.0, "MODE": "MASTER", "MAX_PEERS": 8}
    config = {"PROXY": {"TARGET_SYSTEM": "MASTER-A"}, "SYSTEMS": {"MASTER-A": sys_cfg}}
    ctx = DownlinkContext(
        config=config,
        system_name="MASTER-A",
        sys_cfg=sys_cfg,
        peers={},
        status={
            1: _empty_slot(),
            2: {
                **_empty_slot(),
                "TX_PEER": bytes_4(73010),
                "TX_STREAM_ID": bytes_4(0xCCCCDDDD),
                "TX_TYPE": HBPF_SLT_VHEAD,
                "TX_TIME": 2_000_001.0,
                "TX_TGID": bytes_3(7305),
            },
        },
        connected_count=1,
    )
    peer_id = bytes_4(730039101)
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    ctx.peers[peer_id] = peer
    now = 2_000_000.0
    touch_peer_voice_slot(ctx, peer_id, 2, bytes_4(0xAAAABBBB), bytes_3(7306), pkt_time=now)
    from adn_server.application.routing.downlink import end_peer_voice_slot

    end_peer_voice_slot(ctx, peer_id, 2, bytes_4(0xAAAABBBB), bytes_3(7306), pkt_time=now + 5)
    obp7305 = _vhead(2, 7305, 0xCCCCDDDD)
    assert peer_slot_blocks_downlink(ctx, peer_id, peer, obp7305, pkt_time=now + 8)
    same7306 = _vhead(2, 7306, 0xDDDDEEEE)
    assert not peer_slot_blocks_downlink(ctx, peer_id, peer, same7306, pkt_time=now + 8)


def test_same_static_tg_on_both_slots_delivers_once_on_wire_slot() -> None:
    """TG on TS1+TS2 OPTIONS: one DMRD on the bridge wire slot (not dual fan-out)."""
    peer = {"OPTIONS": b"TS1=730444;TS2=730444;"}
    assert iter_downlink_voice_slots(peer, 1, 730444) == [1]
    assert iter_downlink_voice_slots(peer, 2, 730444) == [2]
    # Subscription still visible on both; delivery collapses in iter_*.
    assert peer_listen_slots(peer, 730444) == [1, 2]


def test_static_tg_on_one_slot_unchanged() -> None:
    peer_ts2 = {"OPTIONS": b"TS2=9140;"}
    assert iter_downlink_voice_slots(peer_ts2, 1, 9140) == [2]
    peer_ts1 = {"OPTIONS": b"TS1=9140;"}
    assert iter_downlink_voice_slots(peer_ts1, 2, 9140) == [1]


def test_hp3icc_style_slot_busy_until_vterm() -> None:
    """P2: active QSO on slot 2 blocks foreign TG until VTERM (pcap HP3ICC pattern)."""
    ctx = _ctx()
    peer_id = bytes_4(714002301)
    peer = {"OPTIONS": b"TS2=7141;SINGLE=1;TIMER=5;"}
    ctx.peers[peer_id] = peer
    now = 2_000_000.0
    touch_peer_voice_slot(ctx, peer_id, 2, bytes_4(0xAAAA), bytes_3(7141), pkt_time=now)
    foreign = _vhead(2, 71442, 0xBBBB)
    assert peer_slot_blocks_downlink(ctx, peer_id, peer, foreign, pkt_time=now + 0.5)
    same_stream = _vhead(2, 71442, 0xAAAA)
    assert not peer_slot_blocks_downlink(ctx, peer_id, peer, same_stream, pkt_time=now + 0.5)
    from adn_server.application.routing.downlink import end_peer_voice_slot

    end_peer_voice_slot(ctx, peer_id, 2, bytes_4(0xAAAA), bytes_3(7141), pkt_time=now + 2)
    assert peer_slot_blocks_downlink(ctx, peer_id, peer, foreign, pkt_time=now + 2.5)
    assert not peer_slot_blocks_downlink(ctx, peer_id, peer, foreign, pkt_time=now + 5.5)
