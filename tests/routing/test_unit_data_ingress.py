"""Unit data ingress: headers, CSBK, reporting."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_inject_ok, assert_report_event
from tests.harness.deterministic import DeterministicScenario, PacketSpec, minimal_config

from adn_server.domain import bytes_4
from adn_server.domain.hbp_protocol import HBPF_SLT_VTERM


@pytest.mark.behavior
def test_unit_data_header_accepted_from_hbp() -> None:
    """Regression: unit-data header (dtype 6) is accepted and reported."""
    scenario = DeterministicScenario(enable_reporting=True)
    base = PacketSpec(call_type="unit", dst_id=5001, stream_id=0x51515151, slot=2)

    ok = scenario.inject_unit("MASTER-A", DeterministicScenario.unit_data_header_spec(base))

    assert_inject_ok(ok)
    assert_report_event(scenario, "UNIT DATA HEADER")
    slot = scenario.protocols["MASTER-A"].STATUS.get(2, {})
    assert slot.get("RX_TYPE", HBPF_SLT_VTERM) == HBPF_SLT_VTERM


def test_unit_data_reports_rx_event_when_reporting_enabled() -> None:
    config = minimal_config(("MASTER-A",))
    scenario = DeterministicScenario(config=config, enable_reporting=True)
    base = PacketSpec(call_type="unit", dst_id=5002, stream_id=0x56565656, slot=2)

    scenario.inject_unit("MASTER-A", DeterministicScenario.unit_data_header_spec(base, dtype_vseq=7))

    assert scenario.report_factory is not None
    assert any("UNIT VCSBK 1/2 DATA BLOCK" in ev for ev in scenario.report_factory.events)


@pytest.mark.behavior
def test_unit_data_csbk_new_stream_is_handled() -> None:
    """Regression: CSBK dtype 3 on new stream is accepted and reported."""
    scenario = DeterministicScenario(enable_reporting=True)
    base = PacketSpec(call_type="unit", dst_id=5003, stream_id=0x63636363, slot=2)

    ok = scenario.inject_unit(
        "MASTER-A",
        DeterministicScenario.unit_data_header_spec(base, dtype_vseq=3),
    )

    assert_inject_ok(ok)
    assert_report_event(scenario, "UNIT CSBK")
    slot = scenario.protocols["MASTER-A"].STATUS.get(2, {})
    assert slot.get("RX_TYPE", HBPF_SLT_VTERM) == HBPF_SLT_VTERM


def test_unit_data_csbk_ignored_when_stream_already_known() -> None:
    scenario = DeterministicScenario()
    base = PacketSpec(call_type="unit", dst_id=5004, stream_id=0x64646464, slot=2)
    stream_bytes = base.data()[16:20]
    scenario.protocols["MASTER-A"].STATUS[2]["RX_STREAM_ID"] = stream_bytes

    ok = scenario.inject_unit(
        "MASTER-A",
        DeterministicScenario.unit_data_header_spec(base, dtype_vseq=3),
    )

    assert ok is True
    assert scenario.capture.packets == []
