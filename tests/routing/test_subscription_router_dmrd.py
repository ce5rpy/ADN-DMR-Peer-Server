"""dmrd_received routes voice via SubscriptionRouter."""

from __future__ import annotations

import pytest

from adn_server.application.subscription.store_sync import replace_store_from_routing_table
from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    active_routing_table,
    add_openbridge_system,
    minimal_config,
)


@pytest.mark.behavior
def test_subscription_router_startup_bridge_voice_parity() -> None:
    """Startup static TG forwards across masters via subscription resolve."""
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] = 10
    bridges = active_routing_table(52090, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.routing.apply_startup_subscriptions()
    replace_store_from_routing_table(scenario.subscription_store, scenario.routing.routing_table_for_report())

    base = PacketSpec(dst_id=52090, stream_id=0x80808080, slot=2)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "MASTER-B", count=2, dst_id=52090)


@pytest.mark.behavior
def test_subscription_router_hbp_slot1() -> None:
    config = minimal_config(("MASTER-A", "MASTER-B"))
    bridges = active_routing_table(730444, (("MASTER-A", 1), ("MASTER-B", 1)))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    replace_store_from_routing_table(scenario.subscription_store, scenario.routing.routing_table_for_report())

    base = PacketSpec(dst_id=730444, stream_id=0xAABBCCDD, slot=1)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "MASTER-B", count=2, dst_id=730444)


@pytest.mark.behavior
def test_subscription_router_store_export_parity() -> None:
    """Store authority export keeps forwards and ACTIVE visible in routing_table_for_report()."""
    config = minimal_config(("MASTER-A", "MASTER-B"))
    bridges = active_routing_table(52090, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.routing._finalize_routing_state()

    base = PacketSpec(dst_id=52090, stream_id=0x90909090, slot=2)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "MASTER-B", count=2, dst_id=52090)
    assert scenario.routing.routing_table_for_report()["52090"][0]["ACTIVE"] is True


@pytest.mark.behavior
def test_obp_to_system_forwards_after_obp_source_sync() -> None:
    """OBP RX must forward after _ensure_obp_source syncs into the subscription store."""
    config = minimal_config(("SYSTEM",))
    add_openbridge_system(config, "OBP-CL")
    config["SYSTEMS"]["SYSTEM"]["TS2_STATIC"] = "7305"
    bridges = active_routing_table(7305, (("OBP-CL", 1), ("SYSTEM", 2)))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.routing._finalize_routing_state()

    base = PacketSpec(dst_id=7305, stream_id=0x28060549, slot=1)
    scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    scenario.inject_obp(
        "OBP-CL",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "SYSTEM", count=2, dst_id=7305)


@pytest.mark.behavior
def test_obp_forwards_when_router_shim_stale_but_store_active() -> None:
    """OBP must not re-import a stale BRIDGES shim over the subscription store."""
    config = minimal_config(("SYSTEM",))
    add_openbridge_system(config, "OBP-CL")
    config["SYSTEMS"]["SYSTEM"]["TS2_STATIC"] = "7305"
    scenario = DeterministicScenario(config=config, routing_table={})
    scenario.routing.apply_startup_subscriptions()

    stale_export = scenario.routing.routing_table_for_report()
    for leg in stale_export.get("7305", []):
        if leg["SYSTEM"] == "SYSTEM":
            leg["ACTIVE"] = False

    base = PacketSpec(dst_id=7305, stream_id=0xABCDEF01, slot=1)
    scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    scenario.inject_obp(
        "OBP-CL",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "SYSTEM", count=2, dst_id=7305)
