# ADN DMR Peer Server - tests infrastructure hbp repeat private call
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

"""REPEAT path through real HBPProtocol for private (unit-to-unit) calls.

Regression: the raw intra-MASTER REPEAT loop was gated on
`call_type in ("group", "vcsbk")`, so two peers registered under the same
MASTER system never saw each other's private calls at all — legacy
(hblink.py master_datagramReceived) repeats every call_type unconditionally.
This test exercises the real infrastructure layer (not the routing-only
harness in tests/harness/deterministic.py, which calls dmrd_received()
directly and never touches this REPEAT loop)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.support.hbp_repeat_stack import build_hbp_repeat_stack

from adn_server.domain import bytes_4

_PEER_TX = bytes_4(730039210)
_PEER_RX = bytes_4(730039101)
_ADDR_TX = ("10.0.0.1", 62001)
_ADDR_RX = ("10.0.0.2", 62002)


def _private_spec() -> PacketSpec:
    return PacketSpec(
        peer_id=730039210,
        rf_src=7300392,
        dst_id=7304011,      # 7-digit subscriber ID, not a talkgroup
        slot=2,
        call_type="unit",
        stream_id=0xA1B2C3D4,
        payload=b"\x00" * 33,
    )


def test_private_call_is_repeated_to_other_peer_on_same_master() -> None:
    stack = build_hbp_repeat_stack(talker_alias=True)
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = _private_spec()

    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    downlink = stack.transport.for_addr(_ADDR_RX)
    assert downlink, "private call must be repeated to the other peer on the same MASTER"
    assert downlink[0][11:15] == _PEER_RX


def test_private_call_reaches_peer_under_inject_only_proxy_with_multiple_peers() -> None:
    """Regression: parse_dmrd_burst_fields() returns None for private (unit) calls by
    design (it's a group/vcsbk-only helper) — _peer_should_receive_dmrd's fallback for
    "parsed is None" under an inject-only multi-peer proxy is `connected_count <= 1`,
    which blocks delivery entirely once a 2nd hotspot connects. Real deployments run
    with PROXY.TARGET_SYSTEM set and many peers, so this was silently dropping every
    private call — reproduced here since build_hbp_repeat_stack's default config has
    no PROXY section (the other tests in this file don't exercise this branch at all)."""
    stack = build_hbp_repeat_stack(talker_alias=True)
    stack.config["PROXY"] = {"TARGET_SYSTEM": stack.system_name}
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = _private_spec()

    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1), _ADDR_TX,
    )

    downlink = stack.transport.for_addr(_ADDR_RX)
    assert downlink, "private call must reach the other peer even under inject-only multi-peer proxy"
    assert downlink[0][11:15] == _PEER_RX


def test_private_call_repeat_leaves_burst_payload_unchanged_when_talker_alias_disabled() -> None:
    stack = build_hbp_repeat_stack(talker_alias=False)
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = _private_spec()

    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    uplink = DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1)
    stack.inject_spec(uplink, _ADDR_TX)

    downlink = stack.transport.for_addr(_ADDR_RX)
    assert len(downlink) == 1
    assert downlink[0][20:53] == uplink.payload
    assert stack.hbp.STATUS.get(2, {}).get("TX_TA_EMB") is None


def test_private_call_repeat_embeds_unit_lc_when_talker_alias_enabled() -> None:
    """Same rules as group calls: inject the configured TA when the source doesn't
    supply its own -- only the LC opt byte differs (LC_OPT_U, subscriber destination
    instead of a talkgroup)."""
    stack = build_hbp_repeat_stack(talker_alias=True)
    stack.register_peer(_PEER_TX, _ADDR_TX, options="TS2=7304;")
    stack.register_peer(_PEER_RX, _ADDR_RX, options="TS2=7304;")
    base = _private_spec()
    uplink = DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1)

    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)
    stack.transport.clear()
    stack.inject_spec(uplink, _ADDR_TX)

    downlink = stack.transport.for_addr(_ADDR_RX)
    assert len(downlink) == 1
    slot_st = stack.hbp.STATUS[2]
    assert slot_st.get("TX_TA_EMB") is not None
    assert slot_st.get("REP_EMB_LC") is not None
    # AMBE voice bits (outside the embedded LC slice) still pass through untouched.
    assert downlink[0][20:53][:14] == uplink.payload[:14]
