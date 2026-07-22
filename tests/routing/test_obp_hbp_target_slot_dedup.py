# ADN DMR Peer Server - OBP to HBP target dual-slot dedup
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

"""OBP-sourced group voice must not double-forward to a MASTER target that has
active bridge legs on both TS1 and TS2 for the same TG.

Reproduces the reported bug: an inject-only MASTER aggregates static TGs from
every connected peer's OPTIONS (some listening on TS1, some on TS2), so its
BRIDGES table legitimately lists the MASTER as an active leg on both slots for
one TG. ``send_peers`` already resolves each peer's real listen slot from its
own OPTIONS regardless of the wire slot (``iter_downlink_voice_slots``), so a
second identical leg to that MASTER delivered the same audio twice — doubling
the downlink rate and making unpaced bridges (e.g. ysf2dmr) sound slow. This
never showed up for locally-originated (HBP) calls because a MASTER never
forwards to itself (SubscriptionRouter skips the source system).
"""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    active_routing_table,
    add_openbridge_system,
    minimal_config,
)

from adn_server.domain import bytes_3


@pytest.mark.behavior
def test_obp_group_voice_forwards_once_to_hbp_target_on_both_slots() -> None:
    """SYSTEM listed on TS1 + TS2 for one TG collapses to a single forward per frame."""
    config = minimal_config(("SYSTEM",))
    add_openbridge_system(config, "OBP-CL")
    bridges = active_routing_table(7305, (("OBP-CL", 1), ("SYSTEM", 1), ("SYSTEM", 2)))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.routing._finalize_routing_state()

    base = PacketSpec(dst_id=7305, stream_id=0x28060549, slot=1)
    scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    scenario.inject_obp(
        "OBP-CL",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    # 2 frames in -> 2 packets out, not 4 (one per redundant TS1/TS2 leg).
    assert_forwarded(scenario, "SYSTEM", count=2, dst_id=7305)


@pytest.mark.behavior
def test_obp_group_voice_keeps_distinct_tgid_translation_legs() -> None:
    """Two legs to the same MASTER with different translated TGIDs are not collapsed."""
    config = minimal_config(("SYSTEM",))
    add_openbridge_system(config, "OBP-CL")
    tg_b = bytes_3(7305)
    translated_tg_b = bytes_3(9305)
    bridges = {
        "7305": [
            {
                "SYSTEM": "OBP-CL", "TS": 1, "TGID": tg_b, "ACTIVE": True,
                "TIMEOUT": 60.0, "TO_TYPE": "ON", "ON": [tg_b], "OFF": [], "RESET": [], "TIMER": 0,
            },
            {
                "SYSTEM": "SYSTEM", "TS": 1, "TGID": tg_b, "ACTIVE": True,
                "TIMEOUT": 60.0, "TO_TYPE": "ON", "ON": [tg_b], "OFF": [], "RESET": [], "TIMER": 0,
            },
        ],
        "#7305": [
            {
                "SYSTEM": "OBP-CL", "TS": 1, "TGID": tg_b, "ACTIVE": True,
                "TIMEOUT": 60.0, "TO_TYPE": "ON", "ON": [tg_b], "OFF": [], "RESET": [], "TIMER": 0,
            },
            {
                "SYSTEM": "SYSTEM", "TS": 2, "TGID": translated_tg_b, "ACTIVE": True,
                "TIMEOUT": 60.0, "TO_TYPE": "ON", "ON": [translated_tg_b], "OFF": [], "RESET": [], "TIMER": 0,
            },
        ],
    }
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.routing._finalize_routing_state()

    base = PacketSpec(dst_id=7305, stream_id=0x28060549, slot=1)
    scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    scenario.inject_obp(
        "OBP-CL",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    # 2 frames, 2 distinct target TGIDs -> 4 packets (not collapsed: real distinct destinations).
    assert_forwarded(scenario, "SYSTEM", count=4)
