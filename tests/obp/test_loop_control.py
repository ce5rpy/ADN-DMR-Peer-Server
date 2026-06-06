"""OBP loop control and VTERM stream lifecycle."""

from __future__ import annotations

from tests.harness.deterministic import (
    DeterministicScenario,
    FakeReportFactory,
    FakeReportSender,
    PacketSpec,
    active_bridge,
    add_openbridge_system,
    patch_bridge_wall_time,
)
from tests.harness.scenarios import obp_bridge_scenario

from adn_server.application.reporting_use_cases import ReportingUseCases
from adn_server.domain import bytes_4, int_id


def test_obp_first_packet_bypasses_rate_control() -> None:
    """First frame of a stream must not enter packets/START rate drop."""
    scenario = obp_bridge_scenario("OBP-CL")
    base = PacketSpec(dst_id=52090, stream_id=0xAABBCCDD, slot=1)

    with patch_bridge_wall_time(scenario.clock):
        ok = scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
        assert ok is not False
        obp_st = scenario.protocols["OBP-CL"].STATUS[bytes_4(base.stream_id)]
        assert obp_st.get("packets", -1) == 0


def test_obp_loop_loser_drops_second_obp_source() -> None:
    """Second OBP on the same stream_id loses loop control after its first burst."""
    scenario = obp_bridge_scenario("OBP-A", "OBP-B")
    stream_id = 0x01020304
    base = PacketSpec(dst_id=52090, stream_id=stream_id, slot=1)

    with patch_bridge_wall_time(scenario.clock):
        scenario.inject_obp("OBP-A", DeterministicScenario.voice_head_spec(base))
        scenario.inject_obp(
            "OBP-A",
            DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
        )
        scenario.inject_obp("OBP-B", DeterministicScenario.voice_head_spec(base))
        ok = scenario.inject_obp(
            "OBP-B",
            DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
        )
        assert not ok


def test_obp_loop_loser_sends_bcsq_once_when_enhanced() -> None:
    """Loop loser sends BCSQ once (not on every subsequent packet)."""
    bridges = active_bridge(52090, (("OBP-A", 1), ("OBP-B", 1), ("MASTER-A", 2)))
    config = DeterministicScenario().config
    add_openbridge_system(config, "OBP-A")
    add_openbridge_system(config, "OBP-B", enhanced=True)
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    scenario = DeterministicScenario(config=config, bridges=bridges)

    stream_id = 0x0D0E0F10
    base = PacketSpec(dst_id=52090, stream_id=stream_id, slot=1)

    with patch_bridge_wall_time(scenario.clock):
        scenario.inject_obp("OBP-A", DeterministicScenario.voice_head_spec(base))
        scenario.inject_obp(
            "OBP-A",
            DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
        )
        scenario.inject_obp("OBP-B", DeterministicScenario.voice_head_spec(base))
        scenario.inject_obp(
            "OBP-B",
            DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
        )
        scenario.inject_obp(
            "OBP-B",
            DeterministicScenario.voice_burst_spec(base, seq=2, dtype_vseq=2),
        )

    assert len(scenario.bcsq_capture) == 1
    bcsq = scenario.bcsq_capture[0]
    assert bcsq.system_name == "OBP-B"
    assert int_id(bcsq.tgid) == 52090
    assert int_id(bcsq.stream_id) == stream_id


def test_obp_vterm_sets_fin_and_drops_late_packets() -> None:
    """After VTERM, late packets from the same OBP stream are ignored (_fin)."""
    scenario = obp_bridge_scenario("OBP-CL")
    scenario.config.setdefault("REPORTS", {})["REPORT"] = True
    scenario.report_factory = FakeReportFactory()
    scenario.reporting = ReportingUseCases(FakeReportSender(scenario.report_factory), scenario.config)
    scenario.bridge._reporting = scenario.reporting

    base = PacketSpec(dst_id=52090, stream_id=0x99887766, slot=1)
    sid = bytes_4(base.stream_id)

    with patch_bridge_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
        scenario.inject_obp(
            "OBP-CL",
            DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
        )
        before = len(scenario.capture.for_system("MASTER-A"))
        scenario.inject_obp(
            "OBP-CL",
            DeterministicScenario.voice_term_spec(base, seq=99),
        )
        after_vterm = len(scenario.capture.for_system("MASTER-A"))
        assert after_vterm >= before

        obp_st = scenario.protocols["OBP-CL"].STATUS[sid]
        assert obp_st.get("_fin") is True

        ok = scenario.inject_obp(
            "OBP-CL",
            DeterministicScenario.voice_burst_spec(base, seq=100, dtype_vseq=1),
        )
        assert not ok
        assert len(scenario.capture.for_system("MASTER-A")) == after_vterm
