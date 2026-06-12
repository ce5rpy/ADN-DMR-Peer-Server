# ADN DMR Peer Server - tests routing rule timer timeout
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

"""Bridge rule_timer timeout behaviour (reactor-thread mutations)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, active_routing_table, patch_routing_wall_time


def test_rule_timer_deactivates_expired_on_bridge() -> None:
    """ON-type bridge entry with TIMER in the past becomes inactive."""
    bridges = active_routing_table(52090, (("MASTER-A", 1), ("MASTER-B", 2)))
    bridges["52090"][0]["TO_TYPE"] = "ON"
    bridges["52090"][0]["ACTIVE"] = True
    bridges["52090"][0]["TIMER"] = 100.0

    scenario = DeterministicScenario(routing_table=bridges)
    scenario.clock.now = 200.0

    with patch_routing_wall_time(scenario.clock):
        scenario.routing.rule_timer_loop()

    entry = scenario.routing.routing_table_for_report()["52090"][0]
    assert entry["ACTIVE"] is False
