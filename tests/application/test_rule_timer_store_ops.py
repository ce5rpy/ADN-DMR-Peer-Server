"""Store-native rule_timer_ops."""

from __future__ import annotations

from adn_server.application.subscription.rule_timer_ops import apply_rule_timer_store
from adn_server.application.subscription.store_sync import replace_store_from_bridges
from adn_server.domain.subscription import SubscriptionPhase
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from tests.harness.deterministic import active_bridge


def test_apply_rule_timer_store_deactivates_expired_on() -> None:
    bridges = active_bridge(52090, (("MASTER-A", 1), ("MASTER-B", 2)))
    bridges["52090"][0]["TO_TYPE"] = "ON"
    bridges["52090"][0]["ACTIVE"] = True
    bridges["52090"][0]["TIMER"] = 100.0
    bridges["52090"][1]["TIMER"] = 300.0

    store = InMemorySubscriptionStore()
    replace_store_from_bridges(store, bridges)
    systems_cfg = {
        "MASTER-A": {"SINGLE_MODE": True},
        "MASTER-B": {"SINGLE_MODE": True},
    }
    apply_rule_timer_store(store, systems_cfg, now=200.0)

    subs = {s.system.value: s for s in store.snapshot()}
    assert subs["MASTER-A"].state.phase == SubscriptionPhase.IDLE
    assert subs["MASTER-B"].state.phase == SubscriptionPhase.ACTIVE
