# ADN DMR Peer Server - tests talker alias routing inject
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

"""Talker Alias bridge/repeat injection."""

from __future__ import annotations

from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    active_routing_table,
    add_openbridge_system,
)
from tests.harness.scenarios import talker_alias_config

from adn_server.domain.talker_alias import DMRA_BLOCK_COUNT, DMRA_OPCODE


def test_talker_alias_inject_dmra_on_bridge_vhead() -> None:
    """Bridge forward sends DMRA blocks once per target stream on VHEAD."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=talker_alias_config(), routing_table=bridges)
    base = PacketSpec(dst_id=91, rf_src=3120001, stream_id=0x90909090)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))

    assert len(scenario.dmra_capture) == 1
    dmra = scenario.dmra_capture[0]
    assert dmra.target_system == "MASTER-B"
    assert 1 <= len(dmra.packets) <= DMRA_BLOCK_COUNT
    assert all(p[:4] == DMRA_OPCODE for p in dmra.packets)
    payload = b"".join(p[8:15] for p in dmra.packets)
    assert b"CE5RPY" in payload


def test_talker_alias_vhead_sent_once_per_target_stream() -> None:
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=talker_alias_config(), routing_table=bridges)
    base = PacketSpec(dst_id=91, rf_src=3120001, stream_id=0x91919191)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert len(scenario.dmra_capture) == 1


def test_talker_alias_both_obp_source_injects_immediately() -> None:
    """both + OBP source (can never carry TA): inject template at VHEAD without waiting."""
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "both"
    add_openbridge_system(config, "OBP-CL")
    bridges = active_routing_table(52090, (("OBP-CL", 2), ("MASTER-A", 2)))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    base = PacketSpec(dst_id=52090, rf_src=3120001, stream_id=0x93939393, slot=2)

    scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))

    assert len(scenario.dmra_capture) == 1
    dmra = scenario.dmra_capture[0]
    assert dmra.target_system == "MASTER-A"
    payload = b"".join(p[8:15] for p in dmra.packets)
    assert b"CE5RPY" in payload


def test_both_mode_without_ta_still_rewrites_group_embedded_lc() -> None:
    """Regression: with no injected TA (TX_TA_EMB None), bursts must still carry the
    destination group LC (legacy bridge.py parity).

    The earlier 'preserve source embedded LC' shortcut left a stale LC on the wire, which
    the receiving MMDVM rejected on TG-rewriting legs -> 'watchdog expired, packet loss'.
    """
    from bitarray import bitarray

    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "both"
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    base = PacketSpec(dst_id=91, rf_src=3120001, stream_id=0x95959595, slot=2)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A", DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1)
    )

    ts_st = scenario.protocols["MASTER-B"].STATUS[2]
    # both + MASTER source: TA overlay deferred until source TA or 2s fallback (see docs).
    assert ts_st.get("TX_TA_EMB") is None
    bursts = [p for p in scenario.capture.for_system("MASTER-B") if p.fields["dtype_vseq"] == 1]
    assert bursts, "voice burst B should be forwarded to MASTER-B"
    bits = bitarray(endian="big")
    bits.frombytes(bursts[-1].fields["dmr_payload"])
    emb = bits[116:148]
    assert emb == ts_st["TX_EMB_LC"][1]  # rewritten to destination group LC...
    assert emb.any()  # ...not the preserved all-zero source embedded LC
