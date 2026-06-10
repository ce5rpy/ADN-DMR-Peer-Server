"""P2-009: dmrd_received with USE_SUBSCRIPTION_ROUTER enabled."""

from __future__ import annotations

import pytest

from adn_server.application.subscription.store_sync import replace_store_from_bridges
from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_bridge, minimal_config


@pytest.mark.behavior
def test_subscription_router_startup_bridge_voice_parity() -> None:
    """Same forwards as legacy BRIDGES scan when USE_SUBSCRIPTION_ROUTER is on."""
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["GLOBAL"]["USE_SUBSCRIPTION_ROUTER"] = True
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    config["SYSTEMS"]["MASTER-A"]["DEFAULT_UA_TIMER"] = 10
    bridges = active_bridge(52090, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=config, bridges=bridges)
    scenario.bridge.apply_startup_bridges()
    replace_store_from_bridges(scenario.subscription_store, scenario.bridge.get_bridges())

    base = PacketSpec(dst_id=52090, stream_id=0x80808080, slot=2)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "MASTER-B", count=2, dst_id=52090)


@pytest.mark.behavior
def test_subscription_router_matches_legacy_flag_off() -> None:
    """USE_SUBSCRIPTION_ROUTER=false keeps legacy BRIDGES scan (default)."""
    config = minimal_config(("MASTER-A", "MASTER-B"))
    bridges = active_bridge(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(config=config, bridges=bridges)

    base = PacketSpec(dst_id=91, stream_id=0x01020304, slot=2)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "MASTER-B", count=2, dst_id=91)


@pytest.mark.behavior
def test_subscription_router_hbp_slot1() -> None:
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["GLOBAL"]["USE_SUBSCRIPTION_ROUTER"] = True
    bridges = active_bridge(730444, (("MASTER-A", 1), ("MASTER-B", 1)))
    scenario = DeterministicScenario(config=config, bridges=bridges)
    replace_store_from_bridges(scenario.subscription_store, scenario.bridge.get_bridges())

    base = PacketSpec(dst_id=730444, stream_id=0xAABBCCDD, slot=1)
    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "MASTER-B", count=2, dst_id=730444)
