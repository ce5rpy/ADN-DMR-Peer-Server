# ADN DMR Peer Server - tests obp loop control
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

"""OBP loop control and VTERM stream lifecycle."""

from __future__ import annotations

from tests.harness.deterministic import (
    DeterministicScenario,
    FakeReportFactory,
    FakeReportSender,
    PacketSpec,
    active_routing_table,
    add_openbridge_system,
    patch_routing_wall_time,
)
from tests.harness.scenarios import obp_bridge_scenario

from adn_server.application.reporting_use_cases import ReportingUseCases
from adn_server.domain import bytes_4, int_id


def test_obp_first_packet_bypasses_rate_control() -> None:
    """First frame of a stream must not enter packets/START rate drop."""
    scenario = obp_bridge_scenario("OBP-CL")
    base = PacketSpec(dst_id=52090, stream_id=0xAABBCCDD, slot=1)

    with patch_routing_wall_time(scenario.clock):
        ok = scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
        assert ok is not False
        obp_st = scenario.protocols["OBP-CL"].STATUS[bytes_4(base.stream_id)]
        assert obp_st.get("packets", -1) == 0


def test_obp_loop_loser_drops_second_obp_source() -> None:
    """Second OBP on the same stream_id loses loop control after its first burst."""
    scenario = obp_bridge_scenario("OBP-A", "OBP-B")
    stream_id = 0x01020304
    base = PacketSpec(dst_id=52090, stream_id=stream_id, slot=1)

    with patch_routing_wall_time(scenario.clock):
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
    bridges = active_routing_table(52090, (("OBP-A", 1), ("OBP-B", 1), ("MASTER-A", 2)))
    config = DeterministicScenario().config
    add_openbridge_system(config, "OBP-A")
    add_openbridge_system(config, "OBP-B", enhanced=True)
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    scenario = DeterministicScenario(config=config, routing_table=bridges)

    stream_id = 0x0D0E0F10
    base = PacketSpec(dst_id=52090, stream_id=stream_id, slot=1)

    with patch_routing_wall_time(scenario.clock):
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
    scenario.routing._reporting = scenario.reporting

    base = PacketSpec(dst_id=52090, stream_id=0x99887766, slot=1)
    sid = bytes_4(base.stream_id)

    with patch_routing_wall_time(scenario.clock):
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
