"""Unit data routing: SUB_MAP, hotspot, gateway, OBP fanout."""

from __future__ import annotations

import pytest
from tests.routing.unit_data_helpers import idle_hbp_slot
from tests.harness.assertions import assert_forwarded, assert_not_forwarded
from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    add_openbridge_system,
    minimal_config,
    parse_dmr_fields,
    patch_routing_wall_time,
)

from adn_server.domain import bytes_3
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD, HBPF_SLT_VTERM


@pytest.mark.behavior
def test_unit_data_sub_map_forwards_to_idle_hbp() -> None:
    config = minimal_config(("MASTER-A", "MASTER-B"))
    dst_sub = 7123456
    config["_SUB_MAP"] = {bytes_3(dst_sub): ("MASTER-B", 2, 1000.0)}
    scenario = DeterministicScenario(config=config)
    scenario.protocols["MASTER-B"].STATUS[2] = idle_hbp_slot()
    base = PacketSpec(call_type="unit", dst_id=dst_sub, stream_id=0x52525252, slot=2)

    scenario.inject_unit("MASTER-A", DeterministicScenario.unit_data_header_spec(base))

    assert_forwarded(scenario, "MASTER-B", count=1, call_type="unit")


def test_unit_data_sub_map_skips_busy_hbp_target() -> None:
    config = minimal_config(("MASTER-A", "MASTER-B"))
    dst_sub = 7123456
    config["_SUB_MAP"] = {bytes_3(dst_sub): ("MASTER-B", 2, 1000.0)}
    scenario = DeterministicScenario(config=config)
    scenario.protocols["MASTER-B"].STATUS[2] = {
        "RX_TYPE": HBPF_SLT_VHEAD,
        "TX_TYPE": HBPF_SLT_VTERM,
        "TX_TIME": scenario.clock.time(),
    }
    base = PacketSpec(call_type="unit", dst_id=dst_sub, stream_id=0x53535353, slot=2)

    scenario.inject_unit("MASTER-A", DeterministicScenario.unit_data_header_spec(base))

    assert_not_forwarded(scenario, "MASTER-B")


@pytest.mark.behavior
def test_unit_data_hotspot_peer_match_forwards_to_idle_hbp() -> None:
    """Regression: hotspot peer ID match forwards unit data to idle MASTER slot."""
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["SYSTEMS"]["MASTER-B"]["PEERS"] = {
        1234567890: {"CALLSIGN": "HS1", "IP": "127.0.0.1", "PORT": 62040},
    }
    config["SYSTEMS"]["MASTER-B"]["GROUP_HANGTIME"] = 0
    scenario = DeterministicScenario(config=config)
    scenario.protocols["MASTER-B"].STATUS[2] = idle_hbp_slot()
    base = PacketSpec(call_type="unit", dst_id=123456, stream_id=0x54545454, slot=2)

    scenario.inject_unit("MASTER-A", DeterministicScenario.unit_data_header_spec(base))

    assert_forwarded(scenario, "MASTER-B", count=1, call_type="unit", dst_id=123456)


def test_unit_data_forwards_to_data_gateway_when_enabled() -> None:
    config = minimal_config(("MASTER-A",))
    config["GLOBAL"]["DATA_GATEWAY"] = True
    add_openbridge_system(config, "DATA-GATEWAY")
    config["SYSTEMS"]["DATA-GATEWAY"]["ENABLED"] = True
    scenario = DeterministicScenario(config=config)
    base = PacketSpec(call_type="unit", dst_id=5005, stream_id=0x65656565, slot=2)

    with patch_routing_wall_time(scenario.clock):
        scenario.inject_unit("MASTER-A", DeterministicScenario.unit_data_header_spec(base))

    assert len(scenario.capture.for_system("DATA-GATEWAY")) == 1


def test_unit_data_fanout_to_other_obp_with_ver_gt_1() -> None:
    config = minimal_config(("MASTER-A",))
    add_openbridge_system(config, "OBP-FAN")
    scenario = DeterministicScenario(config=config)
    base = PacketSpec(call_type="unit", dst_id=1000001, stream_id=0x66666666, slot=2)

    with patch_routing_wall_time(scenario.clock):
        scenario.inject_unit("MASTER-A", DeterministicScenario.unit_data_header_spec(base))

    assert len(scenario.capture.for_system("OBP-FAN")) == 1
    assert parse_dmr_fields(scenario.capture.for_system("OBP-FAN")[0].packet)["call_type"] == "unit"
