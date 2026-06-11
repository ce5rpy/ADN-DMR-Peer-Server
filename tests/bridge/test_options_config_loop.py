"""OPTIONS refresh paths (RPTO, startup, connected peer — no 26s loop, V2-P2-016)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario


def test_options_config_for_system_applies_static_tg_from_yaml_options() -> None:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = "TS2=52090;TIMER=10"
    config["SYSTEMS"]["MASTER-A"]["TS1_STATIC"] = ""
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.bridge.options_config_for_system("MASTER-A")

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg["TS2_STATIC"] == "52090"
    assert "52090" in scenario.bridge.get_bridges()


def test_options_config_for_system_skips_master_without_options() -> None:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"].pop("OPTIONS", None)
    config["SYSTEMS"]["MASTER-B"]["OPTIONS"] = "TS2=91;TIMER=10"
    config["SYSTEMS"]["MASTER-B"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.bridge.options_config_for_system("MASTER-A")
    scenario.bridge.options_config_for_system("MASTER-B")

    assert scenario.config["SYSTEMS"]["MASTER-A"].get("TS2_STATIC", "") == ""
    assert scenario.config["SYSTEMS"]["MASTER-B"]["TS2_STATIC"] == "91"


def test_apply_startup_runs_options_config_for_each_master() -> None:
    """Startup/reload path: YAML OPTIONS without TS*_STATIC still materializes bridges."""
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = "TS2=52090;TIMER=10"
    config["SYSTEMS"]["MASTER-A"]["TS1_STATIC"] = ""
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.bridge.apply_startup_bridges()

    assert scenario.config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] == "52090"
    assert "52090" in scenario.bridge.get_bridges()
