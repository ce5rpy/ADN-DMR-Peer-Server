# ADN DMR Peer Server - tests obp obp rate limit
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

"""OBP rate limit regressions."""

from __future__ import annotations

from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    active_routing_table,
    add_openbridge_system,
    patch_routing_wall_time,
)


def test_obp_rate_limit_uses_start_epoch_not_elapsed() -> None:
    """Regression: OBP must not RATE DROP at normal cadence (packets/START)."""
    bridges = active_routing_table(52090, (("OBP-CL", 1), ("MASTER-A", 2)))
    config = DeterministicScenario().config
    add_openbridge_system(config, "OBP-CL")
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    scenario = DeterministicScenario(config=config, routing_table=bridges)

    with patch_routing_wall_time(scenario.clock):
        base = PacketSpec(dst_id=52090, stream_id=0x11223344, slot=1)
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
        accepted = 0
        for seq in range(1, 25):
            ok = scenario.inject_obp(
                "OBP-CL",
                DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4)),
            )
            if ok is not False:
                accepted += 1
        assert accepted >= 20
