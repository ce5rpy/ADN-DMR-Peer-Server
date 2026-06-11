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
