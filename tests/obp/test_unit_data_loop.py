"""OBP unit-data loop control (HBP/OBP earliest-wins)."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_not_forwarded
from tests.harness.deterministic import DeterministicScenario, PacketSpec, patch_bridge_wall_time
from tests.harness.scenarios import obp_bridge_scenario

from adn_server.domain import bytes_4


@pytest.mark.behavior
def test_obp_unit_data_loop_loser_when_hbp_owns_stream() -> None:
    """Regression: OBP unit-data loses when HBP slot already has RX_STREAM_ID."""
    scenario = obp_bridge_scenario("OBP-CL")
    stream_id = 0x71717171
    scenario.seed_hbp_slot_stream("MASTER-A", 2, stream_id, tgid=52090)
    base = PacketSpec(call_type="unit", dst_id=1000001, stream_id=stream_id, slot=1)

    with patch_bridge_wall_time(scenario.clock):
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

    with patch_bridge_wall_time(scenario.clock):
        scenario.inject_obp("OBP-A", DeterministicScenario.unit_data_header_spec(base))
        scenario.inject_obp("OBP-B", DeterministicScenario.unit_data_header_spec(base))

    assert_not_forwarded(scenario, "MASTER-B")
    obp_b_st = scenario.protocols["OBP-B"].STATUS[bytes_4(stream_id)]
    assert obp_b_st.get("LOOPLOG") is True
