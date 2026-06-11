"""Startup bridge wiring (apply_startup_subscriptions)."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_routing_table, minimal_config


def test_apply_startup_subscriptions_creates_static_ts2_tg() -> None:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] = 10
    scenario = DeterministicScenario(config=config)

    scenario.routing.apply_startup_subscriptions()

    assert "52090" in scenario.routing.routing_table_for_report()
    leg = next(e for e in scenario.routing.routing_table_for_report()["52090"] if e["SYSTEM"] == "MASTER-A")
    assert leg["TS"] == 2
    assert leg["ACTIVE"] is True


def test_apply_startup_subscriptions_creates_default_reflector_bridge() -> None:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_REFLECTOR"] = 310
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] = 10
    scenario = DeterministicScenario(config=config)

    scenario.routing.apply_startup_subscriptions()

    assert "#310" in scenario.routing.routing_table_for_report()


def test_options_config_for_system_matches_startup_static_tg() -> None:
    """RPTO path (options_config_for_system) and startup both materialize the same TS2 leg."""
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = "TS2=52090;TIMER=10"
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.routing.options_config_for_system("MASTER-A")

    assert scenario.config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] == "52090"
    assert "52090" in scenario.routing.routing_table_for_report()

    scenario.routing.apply_startup_subscriptions()
    assert "52090" in scenario.routing.routing_table_for_report()


@pytest.mark.behavior
def test_startup_bridge_routes_voice_after_apply() -> None:
    """Regression: static TG from apply_startup_subscriptions forwards HBP voice to peer MASTER."""
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] = 10
    bridges = active_routing_table(52090, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.routing.apply_startup_subscriptions()

    base = PacketSpec(dst_id=52090, stream_id=0x80808080, slot=2)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "MASTER-B", count=2, dst_id=52090)
