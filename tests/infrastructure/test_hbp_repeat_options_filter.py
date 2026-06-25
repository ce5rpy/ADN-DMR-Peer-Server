# ADN DMR Peer Server - tests infrastructure hbp repeat options filter
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

"""Inject-only proxy: REPEAT and bridge downlink respect per-peer RPTO OPTIONS."""

from __future__ import annotations

import pytest
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.support.hbp_repeat_stack import build_hbp_repeat_stack

from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD, HBPF_SLT_VTERM
from adn_server.infrastructure.hbp_constants import DMRD

pytestmark = pytest.mark.integration

_PEER_TX = bytes_4(730044401)
_PEER_RX_MATCH = bytes_4(730044402)
_PEER_RX_OTHER = bytes_4(730039101)
_ADDR_TX = ("10.0.0.10", 62010)
_ADDR_MATCH = ("10.0.0.11", 62011)
_ADDR_OTHER = ("10.0.0.12", 62012)
_TG = 730444


def _inject_proxy_stack():
    stack = build_hbp_repeat_stack(talker_alias=False, system_name="MASTER-A")
    stack.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    stack.hbp._CONFIG = stack.config
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX_MATCH, _ADDR_MATCH, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX_OTHER, _ADDR_OTHER, options="TS2=91;")
    return stack


def _voice_burst() -> bytes:
    spec = PacketSpec(
        peer_id=int.from_bytes(_PEER_TX, "big"),
        rf_src=7300444,
        dst_id=_TG,
        slot=2,
        stream_id=0x11223344,
        payload=b"\x00" * 33,
    )
    return DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1).data()


def test_repeat_only_reaches_peers_with_matching_options() -> None:
    stack = _inject_proxy_stack()
    stack.inject(_voice_burst(), _ADDR_TX)

    match_pkts = [p for p in stack.transport.for_addr(_ADDR_MATCH) if p[:4] == DMRD]
    other_pkts = [p for p in stack.transport.for_addr(_ADDR_OTHER) if p[:4] == DMRD]
    assert len(match_pkts) == 1
    assert other_pkts == []


def test_standalone_master_blocks_empty_options_witness() -> None:
    """Bridge MASTER without inject-only index still filters by OPTIONS (silent witness)."""
    stack = build_hbp_repeat_stack(talker_alias=False, system_name="MASTER-A")
    silent = bytes_4(730039263)
    addr_silent = ("10.0.0.13", 62013)
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX_MATCH, _ADDR_MATCH, options=f"TS2={_TG};")
    stack.register_peer(silent, addr_silent, options="SINGLE=0;")
    stack.hbp._refresh_connected_peer_count()
    assert not stack.hbp._inject_multi_peer_options_filter()

    stack.transport.clear()
    stack.hbp.send_peers(_voice_burst())

    match_pkts = [p for p in stack.transport.for_addr(_ADDR_MATCH) if p[:4] == DMRD]
    silent_pkts = [p for p in stack.transport.for_addr(addr_silent) if p[:4] == DMRD]
    assert len(match_pkts) == 1
    assert silent_pkts == []


def test_bridge_downlink_after_obp_tx_stamp_reaches_matching_peer() -> None:
    """OBP→MASTER send_peers must deliver when bridge leg stamped TX on STATUS."""
    stack = _inject_proxy_stack()
    burst = _voice_burst()
    now = 1_000_000.0
    stack.hbp.STATUS[2] = {
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": burst[16:20],
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "TX_TGID": burst[8:11],
        "RX_TYPE": HBPF_SLT_VTERM,
    }
    stack.hbp.send_peers(burst)

    match_pkts = [p for p in stack.transport.for_addr(_ADDR_MATCH) if p[:4] == DMRD]
    assert len(match_pkts) == 1


def test_obp_bridge_superframe_after_stale_peer_slot() -> None:
    """OBP downlink must replace stale per-peer session (v2.1.1 burst-track parity)."""
    stack = _inject_proxy_stack()
    ce5rpy = bytes_4(0x2B83833D)
    addr = ("186.67.218.183", 42767)
    stack.register_peer(ce5rpy, addr, options="TS2=730,7305;SINGLE=1;TIMER=5;")
    stream_obp = 0x26B00141
    now = 1_000_000.0
    stack.hbp._peer_voice_slots[ce5rpy] = {
        2: {"stream_id": bytes_4(0x179A0FBC), "tgid": 7305, "time": now - 5.0},
    }
    stack.hbp.STATUS[2] = {
        "TX_PEER": bytes_4(73010),
        "TX_STREAM_ID": bytes_4(stream_obp),
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": now,
        "TX_TGID": bytes_3(7305),
        "RX_TYPE": HBPF_SLT_VTERM,
    }
    base = PacketSpec(
        peer_id=73010,
        rf_src=0x1C892B,
        dst_id=7305,
        slot=2,
        stream_id=stream_obp,
    )
    packets = [DeterministicScenario.voice_head_spec(base).data()]
    for seq, dv in [(1, 1), (2, 2), (3, 3), (4, 4)]:
        packets.append(DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=dv).data())
    packets.append(DeterministicScenario.voice_term_spec(base).data())
    for pkt in packets:
        stack.hbp.send_peers(pkt)
    rx = [p for p in stack.transport.for_addr(addr) if p[:4] == DMRD]
    assert len(rx) == len(packets)


def test_bridge_downlink_send_peers_filters_by_options() -> None:
    stack = _inject_proxy_stack()
    burst = _voice_burst()
    stack.hbp.send_peers(burst)

    match_pkts = [p for p in stack.transport.for_addr(_ADDR_MATCH) if p[:4] == DMRD]
    other_pkts = [p for p in stack.transport.for_addr(_ADDR_OTHER) if p[:4] == DMRD]
    tx_pkts = [p for p in stack.transport.for_addr(_ADDR_TX) if p[:4] == DMRD]
    assert len(match_pkts) == 1
    assert other_pkts == []
    assert len(tx_pkts) == 1


def test_echo_tg_9990_reaches_caller_without_9990_in_options() -> None:
    """Echo/echo downlink must not be blocked by static OPTIONS (TG 9990)."""
    stack = _inject_proxy_stack()
    stack.register_peer(
        bytes_4(730039101),
        ("10.0.0.20", 62020),
        options="TS2=730,730444;",
    )
    spec = PacketSpec(
        peer_id=9990,
        rf_src=7300392,
        dst_id=9990,
        slot=2,
        stream_id=0xAABBCCDD,
        payload=b"\x00" * 33,
    )
    burst = DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1).data()
    caller = bytes_4(730039101)
    stack.hbp.STATUS[2]["RX_PEER"] = caller
    stack.hbp.STATUS[2]["RX_TGID"] = burst[8:11]
    stack.hbp.send_peer(caller, burst)

    pkts = [p for p in stack.transport.for_addr(("10.0.0.20", 62020)) if p[:4] == DMRD]
    assert len(pkts) == 1


def test_server_playback_tg9_reaches_requesting_peer_without_tg9_in_options() -> None:
    """On-demand playback (5000 -> TG 9) must reach the peer that keyed 999x."""
    stack = _inject_proxy_stack()
    caller = bytes_4(730039101)
    other = bytes_4(730039102)
    addr_caller = ("10.0.0.20", 62020)
    addr_other = ("10.0.0.21", 62021)
    stack.register_peer(caller, addr_caller, options="TS2=730,730444;")
    stack.register_peer(other, addr_other, options="TS2=91;")
    spec = PacketSpec(
        peer_id=5000,
        rf_src=5000,
        dst_id=9,
        slot=2,
        stream_id=0xCAFEBABE,
        payload=b"\x00" * 33,
    )
    burst = DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1).data()
    stack.hbp.STATUS[2]["RX_PEER"] = caller
    stack.hbp.send_peers(burst)

    caller_pkts = [p for p in stack.transport.for_addr(addr_caller) if p[:4] == DMRD]
    other_pkts = [p for p in stack.transport.for_addr(addr_other) if p[:4] == DMRD]
    assert len(caller_pkts) == 1
    assert other_pkts == []


def test_on_demand_service_dst_skips_ts2_acl() -> None:
    """Private call to 9991 must not be dropped by TG2 ACL that denies service TGs."""
    from adn_server.application.routing.helpers import is_on_demand_service_dst

    assert is_on_demand_service_dst(9991)
    assert is_on_demand_service_dst(9999)
    assert not is_on_demand_service_dst(9990)
    assert not is_on_demand_service_dst(730444)


def test_foreign_vterm_dropped_while_listening_chile_via_send_peers() -> None:
    """Panama VTERM must not reach a hotspot mid-QSO on Chile (inject-only lab)."""
    from adn_server.domain.hbp_protocol import HBPF_DATA_SYNC, HBPF_SLT_VTERM

    stack = _inject_proxy_stack()
    listener = bytes_4(714002301)
    addr = ("10.0.0.20", 62020)
    stack.register_peer(listener, addr, options="TS2=7141,71442;")
    chile_stream = bytes_4(0x11111111)
    panama_stream = bytes_4(0x22222222)
    chile_spec = PacketSpec(
        peer_id=73010,
        rf_src=100,
        dst_id=7141,
        slot=2,
        stream_id=int.from_bytes(chile_stream, "big"),
    )
    chile_burst = DeterministicScenario.voice_burst_spec(chile_spec, seq=1, dtype_vseq=1).data()
    stack.hbp.send_peer(listener, chile_burst)
    panama_vterm = PacketSpec(
        peer_id=73010,
        rf_src=100,
        dst_id=71442,
        slot=2,
        stream_id=int.from_bytes(panama_stream, "big"),
        frame_type=HBPF_DATA_SYNC,
        dtype_vseq=HBPF_SLT_VTERM,
    ).data()
    stack.hbp.send_peers(panama_vterm)
    pkts = [p for p in stack.transport.for_addr(addr) if p[:4] == DMRD]
    assert len(pkts) == 1
    assert pkts[0][8:11] == bytes_3(7141)
    stack.transport.clear()
    stack.hbp.send_peers(panama_vterm)
    assert [p for p in stack.transport.for_addr(addr) if p[:4] == DMRD] == []


def test_rpto_does_not_overwrite_system_options_on_inject_proxy() -> None:
    stack = _inject_proxy_stack()
    config = stack.config
    rpto_a = b"RPTO" + _PEER_TX + b"TS2=730444;"
    rpto_b = b"RPTO" + _PEER_RX_OTHER + b"TS2=91;"
    stack.hbp._master_datagram_received(rpto_a, _ADDR_TX)
    stack.hbp._master_datagram_received(rpto_b, _ADDR_OTHER)
    assert "OPTIONS" not in config["SYSTEMS"]["MASTER-A"]
