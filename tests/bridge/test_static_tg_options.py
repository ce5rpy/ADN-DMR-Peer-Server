"""Static TG / OPTIONS handling (commits fdf45d3, 4e8a2d0 echo leg restore)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, active_bridge

from adn_server.domain import bytes_3


def _master_with_options(options: str) -> DeterministicScenario:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = options
    config["SYSTEMS"]["MASTER-A"]["TS1_STATIC"] = ""
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = ""
    return DeterministicScenario(config=config)


def test_options_ignores_malformed_ts_tokens() -> None:
    scenario = _master_with_options("TS1=91,A92;TS2=52090;TIMER=10")
    before_ts2 = scenario.config["SYSTEMS"]["MASTER-A"].get("TS2_STATIC", "")

    scenario.bridge.options_config_for_system("MASTER-A")

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg.get("TS1_STATIC", "") in ("", before_ts2)
    assert sys_cfg.get("TS2_STATIC", "") == before_ts2


def test_options_duplicate_fingerprint_restores_prohibited_legs() -> None:
    """Identical RPTO fingerprint still runs _restore_prohibited_static_bridge_legs."""
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = "TS2=9990;TIMER=10"
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "9990"
    config["SYSTEMS"]["MASTER-A"]["_options_static_apply_fp"] = "|9990|10"
    bridges = active_bridge(9990, (("MASTER-A", 2),))
    bridges["9990"] = [
        {
            "SYSTEM": "MASTER-A",
            "TS": 2,
            "TGID": bytes_3(9990),
            "ACTIVE": False,
            "TIMEOUT": 600,
            "TO_TYPE": "STAT",
            "ON": [],
            "OFF": [],
            "RESET": [],
            "TIMER": 0,
        }
    ]
    scenario = DeterministicScenario(config=config, bridges=bridges)

    scenario.bridge.options_config_for_system("MASTER-A")

    leg = next(e for e in scenario.bridge.get_bridges()["9990"] if e["SYSTEM"] == "MASTER-A")
    assert leg["ACTIVE"] is True
    assert leg["TO_TYPE"] == "NONE"


def test_bridge_reset_restores_prohibited_static_legs() -> None:
    """BRIDGERESET after peer loss re-enables YAML static TG 9990 on MASTER."""
    config = DeterministicScenario().config
    sys_cfg = config["SYSTEMS"]["MASTER-A"]
    sys_cfg["TS2_STATIC"] = "9990"
    sys_cfg["OPTIONS"] = "TS2=9990;TIMER=10"
    sys_cfg["_reset"] = True
    sys_cfg["_opt_key"] = "stale"
    sys_cfg["_options_static_apply_fp"] = "|9990|10"

    bridges = active_bridge(9990, (("MASTER-A", 2),))
    for entry in bridges["9990"]:
        if entry["SYSTEM"] == "MASTER-A":
            entry["ACTIVE"] = False
            entry["TO_TYPE"] = "ON"

    scenario = DeterministicScenario(config=config, bridges=bridges)
    scenario.bridge.bridge_reset_loop()

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg["_reset"] is False
    assert "_opt_key" not in sys_cfg
    assert "_options_static_apply_fp" not in sys_cfg

    leg = next(e for e in scenario.bridge.get_bridges()["9990"] if e["SYSTEM"] == "MASTER-A")
    assert leg["ACTIVE"] is True
    assert leg["TO_TYPE"] == "NONE"


def test_options_applies_valid_static_tg_once() -> None:
    scenario = _master_with_options("TS2=52090;TIMER=10")
    scenario.bridge.options_config_for_system("MASTER-A")

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg["TS2_STATIC"] == "52090"
    assert "52090" in scenario.bridge.get_bridges()
    fp = sys_cfg.get("_options_static_apply_fp")
    assert fp == "|52090|10"

    scenario.bridge.options_config_for_system("MASTER-A")
    assert scenario.config["SYSTEMS"]["MASTER-A"].get("_options_static_apply_fp") == fp
