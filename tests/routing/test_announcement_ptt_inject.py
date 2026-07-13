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
from adn_server.domain import bytes_4


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
