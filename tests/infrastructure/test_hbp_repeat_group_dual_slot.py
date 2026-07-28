# ADN DMR Peer Server - tests infrastructure hbp repeat group dual slot
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

"""REPEAT path through real HBPProtocol: peer subscribed to a TG on both
static OPTIONS slots must get the group call on both, regardless of the
source peer's own wire slot.

Regression: the intra-MASTER REPEAT loop (_master_datagram_received) sends
the raw incoming packet unchanged via send_peer(), never going through
iter_downlink_voice_slots()/peer_listen_slots() at all -- unlike send_peers()
(exercised by tests/infrastructure/test_peer_downlink_fanout.py), which
already trusted iter_downlink_voice_slots(). A peer-to-peer call on the same
MASTER (the common case) goes through REPEAT, not send_peers(), so the
TS1+TS2 dual-slot fix landed there without covering the path real traffic
actually uses."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, PacketSpec, parse_dmr_fields
from tests.support.hbp_repeat_stack import build_hbp_repeat_stack

from adn_server.domain import bytes_4
from adn_server.infrastructure.hbp_constants import DMRD

_TG = 730
_PEER_TX = bytes_4(730039110)
_PEER_RX = bytes_4(730039101)
_ADDR_TX = ("10.0.0.1", 62001)
_ADDR_RX = ("10.0.0.2", 62002)


def _group_spec(slot: int) -> PacketSpec:
    return PacketSpec(
        peer_id=int.from_bytes(_PEER_TX, "big"),
        rf_src=7300391,
        dst_id=_TG,
        slot=slot,
        call_type="group",
        stream_id=0xA1B2C3D4,
        payload=b"\x00" * 33,
    )


def test_group_call_on_both_static_slots_repeats_to_both() -> None:
    stack = build_hbp_repeat_stack(talker_alias=False)
    # SINGLE_MODE defaults to True in the generic test scenario config, which
    # pulls in the (unrelated) dynamic-session machinery -- pin it explicitly
    # to False here so this test only exercises the static-OPTIONS path.
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    # No RX_FREQ/TX_FREQ/SLOTS given -> derive_peer_rf_mode defaults to duplex
    # (matches a real MMDVM_HS_Dual_Hat hotspot, which reported duplex here).
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX, _ADDR_RX, options=f"TS1={_TG};TS2={_TG};")

    base = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    downlink = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_RX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in downlink)
    assert slots == [1, 2], (
        "peer with TG on both static slots must be repeated on both, "
        f"regardless of the source's own wire slot -- got {slots}"
    )


def test_group_call_on_one_static_slot_still_repeats_once() -> None:
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX, _ADDR_RX, options=f"TS1={_TG};")

    base = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    downlink = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_RX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in downlink)
    assert slots == [1]


def test_group_call_on_dynamic_tg_keyed_both_slots_repeats_to_both() -> None:
    """SINGLE=0 hotspot that has independently keyed the same dynamic
    (non-static) TG on both slots -- static vs dynamic makes no difference to
    whether a duplex peer should get the call on both."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="")
    rx_pk = bytes_4(730039101)
    stack.config["SYSTEMS"][stack.system_name].setdefault("_PEER_UA_MULTI_TGS", {})[rx_pk] = {
        1: {_TG}, 2: {_TG},
    }

    base = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    downlink = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_RX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in downlink)
    assert slots == [1, 2]


def test_group_call_static_on_one_slot_dynamic_on_other_repeats_to_both() -> None:
    """Real-world case: TG static on TS1, independently keyed dynamically
    (SINGLE=0) on TS2 (e.g. via peer_dynamic_tgs DB restore) -- must repeat
    to both, not just the statically-configured slot."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX, _ADDR_RX, options=f"TS1={_TG};")
    rx_pk = bytes_4(730039101)
    stack.config["SYSTEMS"][stack.system_name].setdefault("_PEER_UA_MULTI_TGS", {})[rx_pk] = {
        2: {_TG},
    }

    base = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    downlink = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_RX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in downlink)
    assert slots == [1, 2]


def test_group_call_on_dynamic_tg_single_mode_stays_exclusive_to_one_slot() -> None:
    """SINGLE=1 ("one exclusive dynamic TG per hotspot, either RF slot; new
    local TX replaces all others" -- register_peer_ua_session) cannot have
    the same TG genuinely active on both slots at once: registering it on
    slot 2 clears slot 1's session. This is intentional exclusivity, not a
    duplex/simultaneous-dual-slot case like static OPTIONS or SINGLE=0 -- it
    must keep collapsing to one slot."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS2={_TG};")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="SINGLE=1;")
    rx_pk = bytes_4(730039101)
    stack.config["SYSTEMS"][stack.system_name].setdefault("_PEER_UA_SESSIONS", {})[rx_pk] = {
        2: {"tgid": _TG, "expires": 0, "source": "local"},
    }

    base = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    downlink = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_RX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in downlink)
    assert slots == [2]
