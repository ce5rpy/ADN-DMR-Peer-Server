# ADN DMR Peer Server - tests routing private voice
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

"""Private (unit) voice routing via SUB_MAP."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, PacketSpec, minimal_config, parse_dmr_fields

from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD


def _private_call_scenario(dst_subscriber: int = 7123456) -> tuple[DeterministicScenario, int]:
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["SYSTEMS"]["MASTER-A"]["PEERS"] = {
        "1001": {"CALLSIGN": "SRC", "IP": "127.0.0.1", "PORT": 62040},
    }
    config["SYSTEMS"]["MASTER-B"]["PEERS"] = {
        "1002": {"CALLSIGN": "DST", "IP": "127.0.0.1", "PORT": 62033},
    }
    config["_SUB_MAP"] = {bytes_3(dst_subscriber): ("MASTER-B", 2, 1000.0)}
    return DeterministicScenario(config=config), dst_subscriber


def test_private_call_forwards_to_subscriber_system() -> None:
    scenario, dst_sub = _private_call_scenario()
    base = PacketSpec(
        call_type="unit",
        dst_id=dst_sub,
        rf_src=3120001,
        stream_id=0xAABBCCDD,
        slot=2,
    )

    scenario.inject_unit("MASTER-A", DeterministicScenario.unit_voice_head_spec(base))
    scenario.inject_unit(
        "MASTER-A",
        DeterministicScenario.unit_voice_burst_spec(base, seq=1),
    )

    forwarded = scenario.capture.for_system("MASTER-B")
    assert len(forwarded) >= 2
    assert all(parse_dmr_fields(p.packet)["call_type"] == "unit" for p in forwarded)


def test_private_call_same_system_does_not_forward() -> None:
    config = minimal_config(("MASTER-A", "MASTER-B"))
    dst_sub = 7123456
    config["_SUB_MAP"] = {bytes_3(dst_sub): ("MASTER-A", 2, 1000.0)}
    scenario = DeterministicScenario(config=config)
    base = PacketSpec(call_type="unit", dst_id=dst_sub, stream_id=0x11223344, slot=2)

    scenario.inject_unit("MASTER-A", DeterministicScenario.unit_voice_head_spec(base))

    assert scenario.capture.packets == []


def test_private_call_collision_drops_new_stream() -> None:
    scenario, dst_sub = _private_call_scenario()
    t0 = scenario.clock.time()
    slot = scenario.protocols["MASTER-A"].STATUS[2]
    slot.update(
        {
            "RX_STREAM_ID": bytes_4(0x99998888),
            "RX_TYPE": HBPF_SLT_VHEAD,
            "RX_RFS": bytes_3(1111111),
            "RX_TIME": t0,
        }
    )
    scenario.clock.advance(0.1)
    base = PacketSpec(
        call_type="unit",
        dst_id=dst_sub,
        rf_src=2222222,
        stream_id=0xDEADBEEF,
        slot=2,
    )

    scenario.inject_unit("MASTER-A", DeterministicScenario.unit_voice_head_spec(base))

    assert scenario.capture.packets == []
