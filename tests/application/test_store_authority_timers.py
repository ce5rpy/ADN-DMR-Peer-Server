"""Subscription store stays aligned after timer and bridge mutations."""

from __future__ import annotations

from adn_server.domain.subscription import SubscriptionPhase
from tests.harness.deterministic import DeterministicScenario, active_bridge, patch_bridge_wall_time


def test_rule_timer_syncs_subscription_store() -> None:
    bridges = active_bridge(52090, (("MASTER-A", 1), ("MASTER-B", 2)))
    bridges["52090"][0]["TO_TYPE"] = "ON"
    bridges["52090"][0]["ACTIVE"] = True
    bridges["52090"][0]["TIMER"] = 100.0

    scenario = DeterministicScenario(bridges=bridges)
    scenario.clock.now = 200.0

    with patch_bridge_wall_time(scenario.clock):
        scenario.bridge.rule_timer_loop()

    assert scenario.bridge.get_bridges()["52090"][0]["ACTIVE"] is False
    subs = scenario.subscription_store.snapshot()
    master_a = next(s for s in subs if s.system.value == "MASTER-A")
    assert master_a.state.phase == SubscriptionPhase.IDLE


def test_finalize_exports_from_subscription_store() -> None:
    bridges = active_bridge(730, (("MASTER-A", 2),))
    scenario = DeterministicScenario(bridges=bridges)
    sub = scenario.subscription_store.snapshot()[0]
    sub.state.phase = SubscriptionPhase.ACTIVE
    scenario.subscription_store.upsert(sub)

    scenario.bridge._finalize_bridges_state()

    exported = scenario.bridge.get_bridges()
    assert exported["730"][0]["ACTIVE"] is True
    assert scenario.subscription_store.snapshot()[0].is_active()
