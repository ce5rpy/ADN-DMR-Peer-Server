# ADN DMR Peer Server - tests application routing table legacy view
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

"""RoutingTableLegacyView: subscription store → legacy BRIDGES shim."""

from __future__ import annotations

from adn_server.application.subscription.routing_table_export import export_routing_table
from adn_server.application.subscription.routing_table_legacy_view import RoutingTableLegacyView
from adn_server.domain import bytes_3
from adn_server.domain.subscription import (
    ActivationPolicy,
    AudioChannel,
    Subscription,
    SubscriptionPhase,
    SubscriptionRole,
    SubscriptionState,
    SystemId,
    TgId,
)
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def _sample_store() -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    store.upsert(
        Subscription(
            channel=AudioChannel(tgid=TgId(730444), slot=1),
            system=SystemId("MASTER-A"),
            target_tgid=TgId(730444),
            role=SubscriptionRole.SINK,
            policy=ActivationPolicy.INBAND,
            state=SubscriptionState(phase=SubscriptionPhase.ACTIVE),
        )
    )
    return store


def test_generate_matches_export_routing_table():
    store = _sample_store()
    view = RoutingTableLegacyView(store)
    now = 1_700_000_000.0
    assert view.generate(now=now) == export_routing_table(store, now=now)
