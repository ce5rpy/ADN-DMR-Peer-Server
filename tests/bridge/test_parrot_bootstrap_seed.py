"""Regression: echo bridge 9990 must route to ECHO (bootstrap seed + VHEAD ON arm)."""

from __future__ import annotations

from adn_server.infrastructure.bootstrap.peer_server import _make_echo_bridges
from tests.bridge.test_echo_bridgereset import _echo_scenario_config
from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import DeterministicScenario, PacketSpec


def _prod_like_config() -> dict:
    config = _echo_scenario_config()
    sys_cfg = config["SYSTEMS"].pop("SYSTEM-82")
    sys_cfg["TS2_STATIC"] = ""
    config["SYSTEMS"]["SYSTEM"] = sys_cfg
    return config


def test_parrot_routing_missing_without_echo_store_seed() -> None:
    scenario = DeterministicScenario(config=_prod_like_config(), bridges={})
    scenario.bridge.apply_startup_bridges()

    base = PacketSpec(dst_id=9990, stream_id=0xABCDEF01, slot=2)
    scenario.inject_hbp("SYSTEM", DeterministicScenario.voice_head_spec(base))

    assert scenario.capture.for_system("ECHO") == []


def test_parrot_routing_works_after_echo_seed_on_vhead() -> None:
    config = _prod_like_config()
    scenario = DeterministicScenario(config=config, bridges=_make_echo_bridges(config))
    scenario.bridge.apply_startup_bridges()

    base = PacketSpec(dst_id=9990, stream_id=0xABCDEF02, slot=2)
    scenario.inject_hbp("SYSTEM", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "SYSTEM",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "ECHO", count=2, dst_id=9990)
