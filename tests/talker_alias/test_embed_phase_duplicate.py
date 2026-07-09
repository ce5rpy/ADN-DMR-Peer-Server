# ADN DMR Peer Server - tests talker alias embed phase duplicate
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

"""TA embed phase machine must ignore byte-identical duplicate voice bursts."""

from __future__ import annotations

from bitarray import bitarray
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.harness.scenarios import talker_alias_config
from tests.support.hbp_repeat_stack import build_hbp_repeat_stack

from adn_server.application.routing_use_cases import RoutingUseCases
from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.dmr.bptc import encode_emblc
from adn_server.domain.dmr.const import LC_OPT
from adn_server.infrastructure.acl_router import InMemoryAclRouter
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from adn_server.infrastructure.talker_alias_emblc import default_ta_emblc_encoder

_EMB_SLICE = slice(116, 148)
_PEER_TX = bytes_4(730039210)
_PEER_RX = bytes_4(730039101)
_ADDR_TX = ("10.0.0.1", 62001)
_ADDR_RX = ("10.0.0.2", 62002)


def _embed_bits(dmrpkt: bytes) -> bitarray:
    bits = bitarray(endian="big")
    bits.frombytes(dmrpkt)
    return bits[_EMB_SLICE]


def _init_repeat_slot(
    bridge: RoutingUseCases,
    *,
    system_name: str = "MASTER-A",
    slot: int = 2,
    stream_id: bytes,
    rf_src: bytes,
    dst_id: bytes,
) -> dict:
    class _Proto:
        STATUS = {slot: {}}

    proto = _Proto()
    protocols = {system_name: proto}
    bridge._get_protocols = lambda: protocols  # type: ignore[method-assign]
    st = proto.STATUS[slot]
    st["REP_STREAM_ID"] = stream_id
    st["REP_EMB_LC"] = encode_emblc(LC_OPT + dst_id + rf_src)
    bridge._init_talker_alias_embed(st, system_name, system_name, rf_src, stream_id)
    return st


def _run_superframe(
    bridge: RoutingUseCases,
    *,
    system_name: str,
    slot: int,
    stream_id: bytes,
    payload: bytes,
    duplicate_e: bool = False,
) -> bytes:
    for dtype in (1, 2, 3, 4):
        bridge.rewrite_repeat_voice_burst(
            system_name, slot, stream_id, dtype, payload,
        )
    if duplicate_e:
        bridge.rewrite_repeat_voice_burst(
            system_name, slot, stream_id, 4, payload,
        )
    return bridge.rewrite_repeat_voice_burst(
        system_name, slot, stream_id, 1, payload,
    )


def test_duplicate_burst_e_does_not_advance_ta_phase() -> None:
    """Byte-identical burst E must not double-advance the embed phase machine."""
    config = talker_alias_config()
    bridge = RoutingUseCases(
        InMemoryAclRouter(),
        config,
        InMemorySubscriptionStore(),
        get_protocols=lambda: {},
        encode_emblc=encode_emblc,
        ta_emblc_encoder=default_ta_emblc_encoder,
    )
    stream_id = bytes_4(0xC0FFEE01)
    rf_src = bytes_3(3120001)
    dst_id = bytes_3(7304)
    payload = b"\x42" + b"\x00" * 32
    st = _init_repeat_slot(
        bridge,
        stream_id=stream_id,
        rf_src=rf_src,
        dst_id=dst_id,
    )

    baseline_next_b = _run_superframe(
        bridge,
        system_name="MASTER-A",
        slot=2,
        stream_id=stream_id,
        payload=payload,
        duplicate_e=False,
    )
    baseline_phase = st.get("TX_TA_PHASE", 0)
    baseline_embed = _embed_bits(baseline_next_b)

    st_dup = _init_repeat_slot(
        bridge,
        stream_id=stream_id,
        rf_src=rf_src,
        dst_id=dst_id,
    )
    dup_next_b = _run_superframe(
        bridge,
        system_name="MASTER-A",
        slot=2,
        stream_id=stream_id,
        payload=payload,
        duplicate_e=True,
    )

    assert st_dup.get("TX_TA_PHASE", 0) == baseline_phase
    assert _embed_bits(dup_next_b) == baseline_embed


def test_repeat_stack_duplicate_burst_matches_non_duplicate_embed() -> None:
    """Integration: duplicated REPEAT burst E keeps the next superframe TA embed aligned."""

    def _play_through(duplicate_e: bool) -> bitarray:
        stack = build_hbp_repeat_stack(talker_alias=True)
        stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
        stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
        base = PacketSpec(
            peer_id=730039210,
            rf_src=7300392,
            dst_id=7304,
            slot=2,
            stream_id=0xA1B2C3D4,
            payload=b"\x77" + b"\x00" * 32,
        )
        stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
        for seq, dtype in enumerate((1, 2, 3, 4), start=1):
            stack.inject_spec(
                DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=dtype),
                _ADDR_TX,
            )
        if duplicate_e:
            stack.inject_spec(
                DeterministicScenario.voice_burst_spec(base, seq=5, dtype_vseq=4),
                _ADDR_TX,
            )
        stack.transport.clear()
        next_seq = 6 if duplicate_e else 5
        stack.inject_spec(
            DeterministicScenario.voice_burst_spec(base, seq=next_seq, dtype_vseq=1),
            _ADDR_TX,
        )
        downlink = stack.transport.for_addr(_ADDR_RX)
        assert downlink, "expected downlink after superframe"
        return _embed_bits(downlink[0][20:53])

    assert _play_through(duplicate_e=False) == _play_through(duplicate_e=True)


def test_two_vheads_emit_dmra_on_repeat_path() -> None:
    """Legacy hblink re-sends DMRA on every VHEAD; REPEAT must not dedupe the second."""
    stack = build_hbp_repeat_stack(talker_alias=True)
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = PacketSpec(
        peer_id=730039210,
        rf_src=7300392,
        dst_id=7304,
        slot=2,
        stream_id=0xA1B2C3D4,
    )

    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    first_dmra = len(stack.dmra_capture)
    assert first_dmra == 1

    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    assert len(stack.dmra_capture) == first_dmra + 1
