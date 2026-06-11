"""Store-native stat_trimmer, bridge_debug, and bridge_reset."""

from __future__ import annotations

from adn_server.application.subscription.bridge_debug_ops import apply_bridge_debug_store
from adn_server.application.subscription.bridge_reset_ops import (
    deactivate_system_legs_store,
    restore_prohibited_static_legs_store,
)
from adn_server.application.subscription.stat_trimmer_ops import apply_stat_trimmer_store
from adn_server.application.subscription.store_sync import replace_store_from_bridges
from adn_server.domain import bytes_3
from adn_server.domain.subscription import SubscriptionPhase
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from tests.harness.deterministic import active_bridge


def _store(bridges: dict) -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    replace_store_from_bridges(store, bridges)
    return store


def test_stat_trimmer_removes_unused_stat_table() -> None:
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
    assert store.snapshot() == ()


def test_bridge_debug_removes_prohibited_numeric_keys() -> None:
    bridges = active_bridge(52090, (("MASTER-A", 2),))
    bridges["5"] = list(bridges["52090"])
    store = _store(bridges)
    apply_bridge_debug_store(store, {"MASTER-A": {"MODE": "MASTER"}}, now=1000.0)
    assert all(s.table_key() != "5" for s in store.snapshot())
    assert any(s.table_key() == "52090" for s in store.snapshot())


def test_deactivate_system_legs_store() -> None:
    store = _store(active_bridge(52090, (("MASTER-A", 2), ("MASTER-B", 2))))
    deactivate_system_legs_store(store, "MASTER-A", now=5000.0)
    master = next(s for s in store.snapshot() if s.system.value == "MASTER-A")
    other = next(s for s in store.snapshot() if s.system.value == "MASTER-B")
    assert master.state.phase == SubscriptionPhase.IDLE
    assert other.is_active()


def test_restore_prohibited_static_leg() -> None:
    bridges = active_bridge(9990, (("MASTER-A", 2),))
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
