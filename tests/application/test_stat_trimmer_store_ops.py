# ADN DMR Peer Server - tests application stat trimmer store ops
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

"""stat_trimmer must not drop OBP STAT bridges while the source leg is active."""

from __future__ import annotations

from adn_server.application.subscription.stat_trimmer_ops import apply_stat_trimmer_store
from adn_server.application.subscription.subscription_queries import store_has_table
from adn_server.application.subscription.subscription_table_ops import ensure_stat_relay_store
from adn_server.domain import bytes_3
from fakes.subscription_store import InMemorySubscriptionStore


def test_stat_trimmer_keeps_obp_stat_bridge_with_inactive_system_legs() -> None:
    store = InMemorySubscriptionStore()
    systems_cfg = {
        "OBP-CL": {"MODE": "OPENBRIDGE", "DEFAULT_UA_TIMER": 10},
        "SYSTEM": {"MODE": "MASTER", "DEFAULT_UA_TIMER": 10},
    }
    ensure_stat_relay_store(store, bytes_3(52090), systems_cfg, now=1000.0)
    assert store_has_table(store, "52090")

    apply_stat_trimmer_store(store)

    assert store_has_table(store, "52090")
