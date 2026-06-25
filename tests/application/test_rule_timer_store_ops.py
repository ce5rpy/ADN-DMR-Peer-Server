# ADN DMR Peer Server - tests application rule timer store ops
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

"""Store-native rule_timer_ops."""

from __future__ import annotations

from tests.harness.deterministic import active_routing_table

from adn_server.application.subscription.rule_timer_ops import apply_rule_timer_store
from adn_server.application.subscription.store_sync import replace_store_from_routing_table
from adn_server.domain.subscription import SubscriptionPhase
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def test_apply_rule_timer_store_deactivates_expired_on() -> None:
    bridges = active_routing_table(52090, (("MASTER-A", 1), ("MASTER-B", 2)))
    bridges["52090"][0]["TO_TYPE"] = "ON"
    bridges["52090"][0]["ACTIVE"] = True
    bridges["52090"][0]["TIMER"] = 100.0
    bridges["52090"][1]["TIMER"] = 300.0

    store = InMemorySubscriptionStore()
    replace_store_from_routing_table(store, bridges)
    systems_cfg = {
        "MASTER-A": {"SINGLE_MODE": True},
        "MASTER-B": {"SINGLE_MODE": True},
    }
    apply_rule_timer_store(store, systems_cfg, now=200.0)

    subs = {s.system.value: s for s in store.snapshot()}
    assert subs["MASTER-A"].state.phase == SubscriptionPhase.IDLE
    assert subs["MASTER-B"].state.phase == SubscriptionPhase.ACTIVE
