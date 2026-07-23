# ADN DMR Peer Server - announcement synthetic PTT inject
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

"""Announcement synthetic PTT inject routing (proxy MASTER + OBP forward)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, PacketSpec, patch_routing_wall_time
from tests.harness.scenarios import obp_bridge_scenario

from adn_server.application.routing.announcement_ptt_inject import (
    announcement_ptt_system,
    inject_announcement_ptt,
)
from adn_server.application.server_voice import DEFAULT_SERVER_VOICE_ID
from adn_server.domain import bytes_4, int_id


def test_announcement_ptt_system_prefers_proxy_target() -> None:
    config = DeterministicScenario().config
    config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    assert announcement_ptt_system(config) == "MASTER-A"


def test_inject_forwards_to_obp_and_peer_master() -> None:
    scenario = obp_bridge_scenario("OBP-CL", tg=91)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    server_id = scenario.config["GLOBAL"]["SERVER_ID"]
    if isinstance(server_id, bytes):
        peer_id = int.from_bytes(server_id[:4], "big")
    else:
        peer_id = int(server_id)
    base = PacketSpec(
        peer_id=peer_id,
        rf_src=DEFAULT_SERVER_VOICE_ID,
        dst_id=91,
        slot=2,
        stream_id=0xA0A0A0A0,
    )
    sid = server_id if isinstance(server_id, bytes) else bytes_4(int(server_id))
    with patch_routing_wall_time(scenario.clock):
        vhead = DeterministicScenario.voice_head_spec(base)
        inject_announcement_ptt(
            scenario.routing,
            "MASTER-A",
            vhead.data(),
            pkt_time=scenario.clock.time(),
            server_id=sid,
        )
        for seq in range(1, 3):
            spec = DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4))
            assert inject_announcement_ptt(
                scenario.routing,
                "MASTER-A",
                spec.data(),
                pkt_time=scenario.clock.time(),
                server_id=sid,
            ) is True
    assert len(scenario.capture.for_system("OBP-CL")) == 3
    assert len(scenario.capture.for_system("MASTER-A")) == 0


def test_inject_does_not_attribute_call_to_real_peer_matching_rf_src() -> None:
    """An announcement whose rf_src (e.g. 1000001) matches a real connected peer's

    login id must never be reported as that peer's call: no RX/TX attribution,
    no dynamic TG learned for it. Regression for the misattribution bug where
    ``resolve_voice_peer_id``'s rf_src fallback fired for synthetic frames.
    """
    scenario = obp_bridge_scenario("OBP-CL", tg=91)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    real_peer_id = DEFAULT_SERVER_VOICE_ID
    scenario.config["SYSTEMS"]["MASTER-A"]["PEERS"] = {
        bytes_4(real_peer_id): {"CONNECTION": "YES", "OPTIONS": b"TS2=91;"},
    }
    server_id = scenario.config["GLOBAL"]["SERVER_ID"]
    sid = server_id if isinstance(server_id, bytes) else bytes_4(int(server_id))
    events: list[str] = []
    scenario.routing._send_routing_event = events.append  # type: ignore[method-assign]
    base = PacketSpec(
        peer_id=int_id(sid),
        rf_src=real_peer_id,
        dst_id=91,
        slot=2,
        stream_id=0xB0B0B0B0,
    )
    with patch_routing_wall_time(scenario.clock):
        vhead = DeterministicScenario.voice_head_spec(base)
        inject_announcement_ptt(
            scenario.routing,
            "MASTER-A",
            vhead.data(),
            pkt_time=scenario.clock.time(),
            server_id=sid,
        )
        for seq in range(1, 3):
            spec = DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4))
            inject_announcement_ptt(
                scenario.routing,
                "MASTER-A",
                spec.data(),
                pkt_time=scenario.clock.time(),
                server_id=sid,
            )

    assert events, "expected at least one GROUP VOICE report"
    rx_events = [e for e in events if e.startswith("GROUP VOICE,START,RX,") or e.startswith("GROUP VOICE,END,RX,")]
    assert rx_events, "expected an RX report for the MASTER-A inject"
    for event in rx_events:
        fields = event.split(",")
        reported_peer = int(fields[5])
        assert reported_peer != real_peer_id
        assert reported_peer == int_id(sid)
        assert fields[-1] == "1"
