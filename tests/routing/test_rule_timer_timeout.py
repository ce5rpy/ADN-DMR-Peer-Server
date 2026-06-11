"""Bridge rule_timer timeout behaviour (reactor-thread mutations)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, active_routing_table, patch_routing_wall_time


def test_rule_timer_deactivates_expired_on_bridge() -> None:
    """ON-type bridge entry with TIMER in the past becomes inactive."""
    bridges = active_routing_table(52090, (("MASTER-A", 1), ("MASTER-B", 2)))
    bridges["52090"][0]["TO_TYPE"] = "ON"
    bridges["52090"][0]["ACTIVE"] = True
    bridges["52090"][0]["TIMER"] = 100.0

    scenario = DeterministicScenario(routing_table=bridges)
    scenario.clock.now = 200.0

    with patch_routing_wall_time(scenario.clock):
        scenario.routing.rule_timer_loop()

    entry = scenario.routing.routing_table_for_report()["52090"][0]
    assert entry["ACTIVE"] is False
