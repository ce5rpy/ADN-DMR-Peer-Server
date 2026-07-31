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


def test_group_call_echoes_to_transmitting_peers_own_other_slot() -> None:
    """New behavior: a repeater transmitting a TG on one slot, that is also
    subscribed (static or dynamic) to that same TG on its OTHER slot, hears
    its own call echoed there too -- that other slot is a genuinely
    independent RF path also tuned to the TG."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    # TG static on TS1 only; transmits on slot 2 -- slot 1 is the "other" slot.
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS1={_TG};")

    base = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    echo = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_TX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in echo)
    assert slots == [1], f"peer should hear itself echoed on its own other slot -- got {slots}"


def test_group_call_echoes_to_own_dynamically_subscribed_other_slot() -> None:
    """Same self-echo, but the other slot's subscription is dynamic (SINGLE=0
    keyed), not static -- static vs dynamic must be treated identically."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options="")
    pk = bytes_4(int.from_bytes(_PEER_TX, "big"))
    stack.config["SYSTEMS"][stack.system_name].setdefault("_PEER_UA_MULTI_TGS", {})[pk] = {
        1: {_TG},
    }

    base = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    echo = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_TX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in echo)
    assert slots == [1], f"peer should hear itself echoed on its dynamically-subscribed other slot -- got {slots}"


def test_group_call_echoes_symmetrically_on_opposite_slot() -> None:
    """Same behavior, transmitting on the opposite slot: TG static on TS2,
    transmits on slot 1 -- echoes back to itself on slot 2."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS2={_TG};")

    base = _group_spec(slot=1)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    echo = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_TX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in echo)
    assert slots == [2], f"peer should hear itself echoed on its own other slot -- got {slots}"


def test_group_call_no_self_echo_when_not_subscribed_on_other_slot() -> None:
    """No TG configured at all -- no self-echo, matching existing (unchanged)
    single-peer behavior."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options="")

    base = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    echo = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_TX and pkt[:4] == DMRD]
    assert echo == []


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


def test_group_call_self_echo_not_blocked_by_own_ingress_when_dynamic_tg_on_both_slots() -> None:
    """Regression: when a TG is dynamically (SINGLE=0) active on both slots,
    peer_downlink_voice_slot used to always resolve to slot 1 regardless of
    which slot was asked about. That made the busy-check for a slot-1-to-2
    self-echo also examine slot 1 -- the peer's own live ingress slot -- so
    the echo was wrongly reported busy even though slot 2 was free."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options="")
    pk = bytes_4(int.from_bytes(_PEER_TX, "big"))
    stack.config["SYSTEMS"][stack.system_name].setdefault("_PEER_UA_MULTI_TGS", {})[pk] = {
        1: {_TG}, 2: {_TG},
    }

    base = _group_spec(slot=1)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    echo = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_TX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in echo)
    assert slots == [2], (
        "self-echo to slot 2 must not be blocked by the source's own ingress "
        f"on slot 1 -- got {slots}"
    )


def test_group_call_self_echo_to_dynamic_slot_not_blocked_by_own_static_slot_ingress() -> None:
    """Regression: TG static on TS1 only, dynamically activated on TS2 by an
    earlier call. peer_hangtime_voice_slots used to always union in the
    static slot (TS1) as a busy-check candidate, via peer_downlink_voice_slot,
    even when the caller only cares about TS2 -- so a later TX on TS1 (the
    static slot, now busy with the source's own ingress) wrongly blocked its
    own self-echo delivery to TS2, even though TS2 was free."""
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.config["SYSTEMS"][stack.system_name]["SINGLE_MODE"] = False
    stack.register_peer(_PEER_TX, _ADDR_TX, options=f"TS1={_TG};SINGLE=0;")

    # First call: TX on TS2 (not in static OPTIONS) -- dynamically activates
    # TS2, and (as a side effect) self-echoes back to the static TS1 slot.
    base_a = _group_spec(slot=2)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base_a), _ADDR_TX)
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base_a, seq=1, dtype_vseq=1), _ADDR_TX,
    )
    stack.inject_spec(DeterministicScenario.voice_term_spec(base_a, seq=2), _ADDR_TX)

    # Second call: TX on TS1 (the static slot) -- must self-echo to TS2,
    # which is now dynamically active from the first call.
    stack.transport.clear()
    base_b = _group_spec(slot=1)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base_b), _ADDR_TX)
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base_b, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    echo = [pkt for pkt, addr in stack.transport.sent if addr == _ADDR_TX and pkt[:4] == DMRD]
    slots = sorted(parse_dmr_fields(pkt)["slot"] for pkt in echo)
    assert slots == [2, 2], (
        "self-echo to the dynamically-active TS2 must not be blocked by the "
        f"source's own busy static TS1 -- got {slots}"
    )
