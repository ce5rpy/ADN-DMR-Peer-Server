# ADN DMR Peer Server - tests infrastructure hbp repeat talker alias
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

"""REPEAT path through real HBPProtocol — catches missing embedded Talker Alias."""

from __future__ import annotations

import pytest
from bitarray import bitarray
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.support.hbp_repeat_stack import build_hbp_repeat_stack

from adn_server.domain import bytes_4
from adn_server.infrastructure.hbp_constants import DMRA

pytestmark = pytest.mark.integration

_PEER_TX = bytes_4(730039210)
_PEER_RX = bytes_4(730039101)
_ADDR_TX = ("10.0.0.1", 62001)
_ADDR_RX = ("10.0.0.2", 62002)
_EMB_SLICE = slice(116, 148)


def _embed_bits(dmrpkt: bytes) -> bitarray:
    bits = bitarray(endian="big")
    bits.frombytes(dmrpkt)
    return bits[_EMB_SLICE]


def _base_spec() -> PacketSpec:
    return PacketSpec(
        peer_id=730039210,
        rf_src=7300392,
        dst_id=7304,
        slot=2,
        stream_id=0xA1B2C3D4,
        payload=b"\x00" * 33,
    )


def test_repeat_downlink_embeds_group_lc_when_talker_alias_enabled() -> None:
    """Regression: raw REPEAT copy left embed LC all-zero; MMDVM never saw TA."""
    stack = build_hbp_repeat_stack(talker_alias=True)
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = _base_spec()
    uplink_burst = DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1)

    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(uplink_burst, _ADDR_TX)

    downlink = stack.transport.for_addr(_ADDR_RX)
    assert len(downlink) == 1
    assert downlink[0][11:15] == _PEER_RX

    uplink_emb = _embed_bits(uplink_burst.payload)
    downlink_emb = _embed_bits(downlink[0][20:53])
    assert downlink_emb != uplink_emb
    slot_st = stack.hbp.STATUS[2]
    assert slot_st.get("TX_TA_EMB") is not None
    assert downlink_emb == slot_st["REP_EMB_LC"][1]


def test_repeat_sends_dmra_and_embed_on_vhead() -> None:
    """MMDVM may ignore DMRA UDP; embed in DMRD must still be prepared on VHEAD."""
    stack = build_hbp_repeat_stack(talker_alias=True)
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = _base_spec()

    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)

    assert stack.dmra_capture, "expected inject DMRA on VHEAD"
    packets, exclude = stack.dmra_capture[0]
    assert exclude == _PEER_TX
    assert all(p[:4] == DMRA for p in packets)
    dmra_to_rx = [p for p, _ in stack.transport.sent if p[:4] == DMRA and _ == _ADDR_RX]
    assert dmra_to_rx, "DMRA should reach listening peer (legacy path)"
    assert stack.hbp.STATUS[2].get("REP_STREAM_ID") == bytes_4(base.stream_id)


def test_repeat_leaves_burst_payload_unchanged_when_talker_alias_disabled() -> None:
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = _base_spec()
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    uplink = DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1)
    stack.inject_spec(uplink, _ADDR_TX)

    downlink = stack.transport.for_addr(_ADDR_RX)
    assert len(downlink) == 1
    assert downlink[0][20:53] == uplink.payload
    assert stack.hbp.STATUS[2].get("TX_TA_EMB") is None


def test_repeat_overlays_ta_on_second_superframe_cycle() -> None:
    """After bursts B–E, the next B should carry TA embed (alternate superframes)."""
    stack = build_hbp_repeat_stack(talker_alias=True)
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = _base_spec()
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)

    for seq, dtype in enumerate((1, 2, 3, 4), start=1):
        stack.inject_spec(
            DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=dtype),
            _ADDR_TX,
        )

    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=5, dtype_vseq=1),
        _ADDR_TX,
    )
    downlink = stack.transport.for_addr(_ADDR_RX)
    assert downlink
    slot_st = stack.hbp.STATUS[2]
    ta_emb = slot_st.get("TX_TA_EMB")
    assert ta_emb is not None
    bits = bitarray(endian="big")
    bits.frombytes(downlink[0][20:53])
    phase = slot_st.get("TX_TA_PHASE", 0)
    assert bits[_EMB_SLICE] == ta_emb[phase][1]
