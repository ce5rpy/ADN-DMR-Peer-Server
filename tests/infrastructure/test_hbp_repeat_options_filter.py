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

from adn_server.domain import bytes_4
from adn_server.infrastructure.hbp_constants import DMRD
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.support.hbp_repeat_stack import build_hbp_repeat_stack

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


def test_repeat_remaps_slot_to_peer_options_ts() -> None:
    """Simplex TS2 TX / TG 7144 → duplex TS1=7144 receives DMRD on TS1 (slot bit flip)."""
    stack = build_hbp_repeat_stack(talker_alias=False, system_name="MASTER-A")
    stack.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    stack.hbp._CONFIG = stack.config
    simplex = bytes_4(730002)
    duplex = bytes_4(730001)
    addr_simplex = ("10.0.0.31", 62031)
    addr_duplex = ("10.0.0.30", 62030)
    stack.register_peer(simplex, addr_simplex, options="TS2=7144;")
    stack.register_peer(duplex, addr_duplex, options="TS1=7144;TS2=714,71442;")

    spec = PacketSpec(
        peer_id=int.from_bytes(simplex, "big"),
        rf_src=730002,
        dst_id=7144,
        slot=2,
        stream_id=0x22334455,
        payload=b"\x00" * 33,
    )
    burst = DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1).data()
    stack.inject(burst, addr_simplex)

    duplex_pkts = [p for p in stack.transport.for_addr(addr_duplex) if p[:4] == DMRD]
    assert len(duplex_pkts) == 1
    assert not (duplex_pkts[0][15] & 0x80)


def test_repeat_cross_slot_static_tg_downlink() -> None:
    """Voice on TS1 reaches hotspot that lists the TG only on TS2 (PR #2 parity)."""
    stack = build_hbp_repeat_stack(talker_alias=False, system_name="MASTER-A")
    stack.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    stack.config["REPORTS"] = {"REPORT": True}
    stack.hbp._CONFIG = stack.config
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS1={_TG};")
    stack.register_peer(_PEER_RX_MATCH, _ADDR_MATCH, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX_OTHER, _ADDR_OTHER, options="TS2=91;")

    spec = PacketSpec(
        peer_id=int.from_bytes(_PEER_TX, "big"),
        rf_src=7300444,
        dst_id=_TG,
        slot=1,
        stream_id=0x11223344,
        payload=b"\x00" * 33,
    )
    stack.inject(DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1).data(), _ADDR_TX)

    match_pkts = [p for p in stack.transport.for_addr(_ADDR_MATCH) if p[:4] == DMRD]
    other_pkts = [p for p in stack.transport.for_addr(_ADDR_OTHER) if p[:4] == DMRD]
    assert len(match_pkts) == 1
    assert other_pkts == []


def test_repeat_cross_slot_emits_downlink_start_tx_report() -> None:
    """REPEAT downlink reports START,TX with OPTIONS slot (monitor CTABLE parity with OBP bridge)."""
    stack = build_hbp_repeat_stack(talker_alias=False, system_name="MASTER-A")
    stack.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    stack.config["REPORTS"] = {"REPORT": True}
    stack.hbp._CONFIG = stack.config
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS1={_TG};")
    stack.register_peer(_PEER_RX_MATCH, _ADDR_MATCH, options=f"TS2={_TG};")

    spec = PacketSpec(
        peer_id=int.from_bytes(_PEER_TX, "big"),
        rf_src=7300444,
        dst_id=_TG,
        slot=1,
        stream_id=0x22334455,
        payload=b"\x00" * 33,
    )
    stack.inject(DeterministicScenario.voice_head_spec(spec).data(), _ADDR_TX)

    tx_starts = [
        e for e in stack.report_factory.events
        if e.startswith(f"GROUP VOICE,START,TX,{stack.system_name},")
    ]
    assert len(tx_starts) == 1
    parts = tx_starts[0].split(",")
    assert int(parts[7]) == 2
    assert int(parts[8]) == _TG


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


def test_rpto_does_not_overwrite_system_options_on_inject_proxy() -> None:
    stack = _inject_proxy_stack()
    config = stack.config
    rpto_a = b"RPTO" + _PEER_TX + b"TS2=730444;"
    rpto_b = b"RPTO" + _PEER_RX_OTHER + b"TS2=91;"
    stack.hbp._master_datagram_received(rpto_a, _ADDR_TX)
    stack.hbp._master_datagram_received(rpto_b, _ADDR_OTHER)
    assert "OPTIONS" not in config["SYSTEMS"]["MASTER-A"]
