# ADN DMR Peer Server - tests application timer store ops
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

"""Store-native stat_trimmer, bridge_debug, and bridge_reset."""

from __future__ import annotations

from tests.harness.deterministic import active_routing_table

from adn_server.application.subscription.stat_trimmer_ops import apply_stat_trimmer_store
from adn_server.application.subscription.store_sync import replace_store_from_routing_table
from adn_server.application.subscription.subscription_debug_ops import apply_subscription_debug_store
from adn_server.application.subscription.subscription_reset_ops import (
    deactivate_system_legs_store,
    restore_prohibited_static_legs_store,
)
from adn_server.domain import bytes_3
from adn_server.domain.subscription import SubscriptionPhase
from fakes.subscription_store import InMemorySubscriptionStore


def _store(bridges: dict) -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    replace_store_from_routing_table(store, bridges)
    return store


def test_stat_trimmer_keeps_obp_stat_table_while_source_active() -> None:
    """Active OBP STAT source must not be trimmed before SYSTEM legs are activated."""
    tg = bytes_3(12345)
    bridges = {
        "12345": [
            {
                "SYSTEM": "OBP-CL",
                "TS": 1,
                "TGID": tg,
                "ACTIVE": True,
                "TIMEOUT": "",
                "TO_TYPE": "STAT",
                "ON": [],
                "OFF": [],
                "RESET": [],
                "TIMER": 0,
            },
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": tg,
                "ACTIVE": False,
                "TIMEOUT": 600.0,
                "TO_TYPE": "ON",
                "ON": [tg],
                "OFF": [],
                "RESET": [],
                "TIMER": 0,
            },
        ]
    }
    store = _store(bridges)
    apply_stat_trimmer_store(store)
    assert len(store.snapshot()) == 2


def test_stat_trimmer_removes_unused_stat_table_when_source_idle() -> None:
    tg = bytes_3(12345)
    bridges = {
        "12345": [
            {
                "SYSTEM": "OBP-CL",
                "TS": 1,
                "TGID": tg,
                "ACTIVE": False,
                "TIMEOUT": "",
                "TO_TYPE": "STAT",
                "ON": [],
                "OFF": [],
                "RESET": [],
                "TIMER": 0,
            },
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": tg,
                "ACTIVE": False,
                "TIMEOUT": 600.0,
                "TO_TYPE": "ON",
                "ON": [tg],
                "OFF": [],
                "RESET": [],
                "TIMER": 0,
            },
        ]
    }
    store = _store(bridges)
    apply_stat_trimmer_store(store)
    assert store.snapshot() == ()


def test_bridge_debug_removes_prohibited_numeric_keys() -> None:
    bridges = active_routing_table(52090, (("MASTER-A", 2),))
    bridges["5"] = list(bridges["52090"])
    store = _store(bridges)
    apply_subscription_debug_store(store, {"MASTER-A": {"MODE": "MASTER"}}, now=1000.0)
    assert all(s.table_key() != "5" for s in store.snapshot())
    assert any(s.table_key() == "52090" for s in store.snapshot())


def test_deactivate_system_legs_store() -> None:
    store = _store(active_routing_table(52090, (("MASTER-A", 2), ("MASTER-B", 2))))
    deactivate_system_legs_store(store, "MASTER-A", now=5000.0)
    master = next(s for s in store.snapshot() if s.system.value == "MASTER-A")
    other = next(s for s in store.snapshot() if s.system.value == "MASTER-B")
    assert master.state.phase == SubscriptionPhase.IDLE
    assert other.is_active()


def test_restore_prohibited_static_leg() -> None:
    bridges = active_routing_table(9990, (("MASTER-A", 2),))
    for entry in bridges["9990"]:
        if entry["SYSTEM"] == "MASTER-A":
            entry["ACTIVE"] = False
            entry["TO_TYPE"] = "ON"
    store = _store(bridges)
    sys_cfg = {
        "MODE": "MASTER",
        "ENABLED": True,
        "TS2_STATIC": "9990",
        "USE_ACL": False,
    }
    restore_prohibited_static_legs_store(store, "MASTER-A", sys_cfg, lambda *_a: True, now=100.0)
    leg = next(s for s in store.snapshot() if s.system.value == "MASTER-A")
    assert leg.is_active()
    assert leg.role.value == "echo"
