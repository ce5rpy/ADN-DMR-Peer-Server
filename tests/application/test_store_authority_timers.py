# ADN DMR Peer Server - tests application store authority timers
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

"""Subscription store stays aligned after timer and bridge mutations."""

from __future__ import annotations

from adn_server.domain.subscription import SubscriptionPhase
from tests.harness.deterministic import DeterministicScenario, active_routing_table, patch_routing_wall_time


def test_rule_timer_syncs_subscription_store() -> None:
    bridges = active_routing_table(52090, (("MASTER-A", 1), ("MASTER-B", 2)))
    bridges["52090"][0]["TO_TYPE"] = "ON"
    bridges["52090"][0]["ACTIVE"] = True
    bridges["52090"][0]["TIMER"] = 100.0

    scenario = DeterministicScenario(routing_table=bridges)
    scenario.clock.now = 200.0

    with patch_routing_wall_time(scenario.clock):
        scenario.routing.rule_timer_loop()

    assert scenario.routing.routing_table_for_report()["52090"][0]["ACTIVE"] is False
    subs = scenario.subscription_store.snapshot()
    master_a = next(s for s in subs if s.system.value == "MASTER-A")
    assert master_a.state.phase == SubscriptionPhase.IDLE


def test_finalize_exports_from_subscription_store() -> None:
    bridges = active_routing_table(730, (("MASTER-A", 2),))
    scenario = DeterministicScenario(routing_table=bridges)
    sub = scenario.subscription_store.snapshot()[0]
    sub.state.phase = SubscriptionPhase.ACTIVE
    scenario.subscription_store.upsert(sub)

    scenario.routing._finalize_routing_state()

    exported = scenario.routing.routing_table_for_report()
    assert exported["730"][0]["ACTIVE"] is True
    assert scenario.subscription_store.snapshot()[0].is_active()
