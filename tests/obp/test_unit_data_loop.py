# ADN DMR Peer Server - tests obp unit data loop
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

"""OBP unit-data loop control (HBP/OBP earliest-wins)."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_not_forwarded
from tests.harness.deterministic import DeterministicScenario, PacketSpec, patch_routing_wall_time
from tests.harness.scenarios import obp_bridge_scenario

from adn_server.domain import bytes_4


@pytest.mark.behavior
def test_obp_unit_data_loop_loser_when_hbp_owns_stream() -> None:
    """Regression: OBP unit-data loses when HBP slot already has RX_STREAM_ID."""
    scenario = obp_bridge_scenario("OBP-CL")
    stream_id = 0x71717171
    scenario.seed_hbp_slot_stream("MASTER-A", 2, stream_id, tgid=52090)
    base = PacketSpec(call_type="unit", dst_id=1000001, stream_id=stream_id, slot=1)

    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.unit_data_header_spec(base))

    assert_not_forwarded(scenario, "MASTER-B")
    obp_st = scenario.protocols["OBP-CL"].STATUS[bytes_4(stream_id)]
    assert obp_st.get("LOOPLOG") is True


@pytest.mark.behavior
def test_obp_unit_data_loop_loser_for_second_obp_source() -> None:
    """Regression: second OBP source loses unit-data loop to the first."""
    scenario = obp_bridge_scenario("OBP-A", "OBP-B")
    stream_id = 0x72727272
    base = PacketSpec(call_type="unit", dst_id=1000001, stream_id=stream_id, slot=1)

    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-A", DeterministicScenario.unit_data_header_spec(base))
        scenario.inject_obp("OBP-B", DeterministicScenario.unit_data_header_spec(base))

    assert_not_forwarded(scenario, "MASTER-B")
    obp_b_st = scenario.protocols["OBP-B"].STATUS[bytes_4(stream_id)]
    assert obp_b_st.get("LOOPLOG") is True
