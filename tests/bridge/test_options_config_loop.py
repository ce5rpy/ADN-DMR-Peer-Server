"""OPTIONS timer loop (options_config_loop, 26s refresh)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario


def test_options_config_loop_applies_static_tg_from_options() -> None:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = "TS2=52090;TIMER=10"
    config["SYSTEMS"]["MASTER-A"]["TS1_STATIC"] = ""
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.bridge.options_config_loop()

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg["TS2_STATIC"] == "52090"
    assert "52090" in scenario.bridge.get_bridges()


def test_options_config_loop_skips_master_without_options() -> None:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"].pop("OPTIONS", None)
    config["SYSTEMS"]["MASTER-B"]["OPTIONS"] = "TS2=91;TIMER=10"
    config["SYSTEMS"]["MASTER-B"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.bridge.options_config_loop()

    assert scenario.config["SYSTEMS"]["MASTER-A"].get("TS2_STATIC", "") == ""
    assert scenario.config["SYSTEMS"]["MASTER-B"]["TS2_STATIC"] == "91"
