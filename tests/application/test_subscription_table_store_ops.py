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

from tests.harness.deterministic import active_routing_table, minimal_config

from adn_server.application.subscription.obp_source_ops import (
    ensure_obp_source_for_tg_store,
    obp_source_needs_ensure,
)
from adn_server.application.subscription.store_sync import replace_store_from_routing_table
from adn_server.application.subscription.subscription_table_ops import (
    ensure_dynamic_relay_store,
    make_static_tg_store,
)
from adn_server.domain import bytes_3
from fakes.subscription_store import InMemorySubscriptionStore


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
    assert obp_source_needs_ensure(store, "OBP-CL", "7305", 7305) is True
    ensure_obp_source_for_tg_store(store, "OBP-CL", "7305", bytes_3(7305), 7305, now=500.0)
    obp = next(s for s in store.snapshot() if s.system.value == "OBP-CL")
    assert obp.is_active()
    assert obp_source_needs_ensure(store, "OBP-CL", "7305", 7305) is False


def test_obp_source_needs_ensure_false_when_no_bridge_table() -> None:
    store = _store()
    assert obp_source_needs_ensure(store, "OBP-CL", "7305", 7305) is False


def test_obp_source_needs_ensure_false_when_obp_source_already_active() -> None:
    bridges = active_routing_table(7305, (("OBP-CL", 1), ("MASTER-A", 2)))
    store = _store(bridges)
    assert obp_source_needs_ensure(store, "OBP-CL", "7305", 7305) is False


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


def test_master_dynamic_tg_slots_single_mode() -> None:
    """SINGLE=1 UA session is detected for a dynamic TG not in OPTIONS."""
    from adn_server.application.routing.helpers import master_dynamic_tg_slots
    from adn_server.domain import bytes_4

    sys_cfg = {"_PEER_UA_SESSIONS": {bytes_4(730039101): {2: {"tgid": 7300, "expires": 9999999.0}}}}
    assert master_dynamic_tg_slots(sys_cfg, 7300, now=1000.0) == {2}


def test_master_dynamic_tg_slots_multi_mode() -> None:
    """SINGLE=0 multi-dynamic TG set is detected."""
    from adn_server.application.routing.helpers import master_dynamic_tg_slots
    from adn_server.domain import bytes_4

    sys_cfg = {"_PEER_UA_MULTI_TGS": {bytes_4(730039101): {2: {7300, 7305}}}}
    assert master_dynamic_tg_slots(sys_cfg, 7300, now=1000.0) == {2}


def test_master_dynamic_tg_slots_expired_single() -> None:
    """Expired SINGLE=1 session is not detected."""
    from adn_server.application.routing.helpers import master_dynamic_tg_slots
    from adn_server.domain import bytes_4

    sys_cfg = {"_PEER_UA_SESSIONS": {bytes_4(730039101): {2: {"tgid": 7300, "expires": 500.0}}}}
    assert master_dynamic_tg_slots(sys_cfg, 7300, now=1000.0) == set()


def test_apply_static_tg_to_bridge_activates_dynamic_tg() -> None:
    """A dynamic TG not in OPTIONS is activated when a peer has an active UA session for it."""
    from tests.harness.deterministic import DeterministicScenario, add_openbridge_system

    from adn_server.domain import bytes_4

    config = minimal_config(("MASTER-A",))
    add_openbridge_system(config, "OBP-CL")
    config["SYSTEMS"]["MASTER-A"]["_PEER_UA_SESSIONS"] = {
        bytes_4(730039101): {2: {"tgid": 7300, "expires": 9999999.0}}
    }
    scenario = DeterministicScenario(config)
    scenario.routing.ensure_dynamic_relay(bytes_3(7300), "MASTER-A", 2, 10.0)
    # Simulate OBP-CL/TS1 source active (as _ensure_obp_source_for_tg would do)
    scenario.routing._ensure_obp_source_for_tg("OBP-CL", "7300", bytes_3(7300), 7300)
    # Before fix: SYSTEM/7300/TS2 is IDLE, OBP traffic can't bridge
    scenario.routing.apply_static_tg_to_bridge(7300)
    legs = [
        s for s in scenario.subscription_store.snapshot()
        if s.system.value == "MASTER-A" and int(s.target_tgid) == 7300
    ]
    ts2 = next(s for s in legs if int(s.channel.slot) == 2)
    assert ts2.is_active(), "SYSTEM TS2 leg for dynamic TG 7300 should be ACTIVE"
