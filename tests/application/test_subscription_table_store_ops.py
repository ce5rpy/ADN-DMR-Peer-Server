# ADN DMR Peer Server - tests application subscription table store ops
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

"""Store-native bridge table and OBP source ops."""

from __future__ import annotations

from adn_server.application.subscription.subscription_table_ops import (
    ensure_dynamic_relay_store,
    make_static_tg_store,
)
from adn_server.application.subscription.obp_source_ops import ensure_obp_source_for_tg_store
from adn_server.application.subscription.store_sync import replace_store_from_routing_table
from adn_server.domain import bytes_3
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from tests.harness.deterministic import active_routing_table, minimal_config


def _store(bridges: dict | None = None) -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    if bridges:
        replace_store_from_routing_table(store, bridges)
    return store


def test_make_static_tg_store_creates_active_off_leg() -> None:
    config = minimal_config(("MASTER-A",))
    store = _store()
    make_static_tg_store(
        store,
        52090,
        2,
        10.0,
        "MASTER-A",
        config["SYSTEMS"],
        now=1000.0,
        single_mode=False,
    )
    leg = next(s for s in store.snapshot() if s.system.value == "MASTER-A" and int(s.channel.slot) == 2)
    assert leg.is_active()


def test_ensure_obp_source_activates_ts1_leg() -> None:
    bridges = active_routing_table(7305, (("OBP-CL", 1), ("MASTER-A", 2)))
    for entry in bridges["7305"]:
        if entry["SYSTEM"] == "OBP-CL":
            entry["ACTIVE"] = False
    store = _store(bridges)
    ensure_obp_source_for_tg_store(store, "OBP-CL", "7305", bytes_3(7305), 7305, now=500.0)
    obp = next(s for s in store.snapshot() if s.system.value == "OBP-CL")
    assert obp.is_active()


def test_ensure_dynamic_relay_store_obp_leg() -> None:
    config = minimal_config(("MASTER-A",))
    add_obp = {
        "OBP-CL": {
            "MODE": "OPENBRIDGE",
            "ENABLED": True,
            "IP": "127.0.0.1",
            "PORT": 0,
        }
    }
    config["SYSTEMS"].update(add_obp)
    store = _store()
    ensure_dynamic_relay_store(store, 7305, "MASTER-A", 2, 10.0, config["SYSTEMS"], now=1.0)
    obp = next(s for s in store.snapshot() if s.system.value == "OBP-CL")
    assert obp.is_active()
