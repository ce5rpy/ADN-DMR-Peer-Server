"""Static TG / OPTIONS handling (commits fdf45d3, 4e8a2d0 echo leg restore)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, active_routing_table, add_openbridge_system

from adn_server.domain import bytes_3, bytes_4


def _master_with_options(options: str) -> DeterministicScenario:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = options
    config["SYSTEMS"]["MASTER-A"]["TS1_STATIC"] = ""
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = ""
    return DeterministicScenario(config=config)


def test_options_ignores_malformed_ts_tokens() -> None:
    scenario = _master_with_options("TS1=91,A92;TS2=52090;TIMER=10")
    before_ts2 = scenario.config["SYSTEMS"]["MASTER-A"].get("TS2_STATIC", "")

    scenario.routing.options_config_for_system("MASTER-A")

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg.get("TS1_STATIC", "") in ("", before_ts2)
    assert sys_cfg.get("TS2_STATIC", "") == before_ts2


def test_options_duplicate_fingerprint_restores_prohibited_legs() -> None:
    """Identical RPTO fingerprint still runs _restore_prohibited_static_bridge_legs."""
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = "TS2=9990;TIMER=10"
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "9990"
    config["SYSTEMS"]["MASTER-A"]["_options_static_apply_fp"] = "|9990|10|1"
    bridges = active_routing_table(9990, (("MASTER-A", 2),))
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
    scenario = DeterministicScenario(config=config, routing_table=bridges)

    scenario.routing.options_config_for_system("MASTER-A")

    leg = next(e for e in scenario.routing.routing_table_for_report()["9990"] if e["SYSTEM"] == "MASTER-A")
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

    bridges = active_routing_table(9990, (("MASTER-A", 2),))
    for entry in bridges["9990"]:
        if entry["SYSTEM"] == "MASTER-A":
            entry["ACTIVE"] = False
            entry["TO_TYPE"] = "ON"

    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.routing.subscription_reset_loop()

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg["_reset"] is False
    assert "_opt_key" not in sys_cfg
    assert "_options_static_apply_fp" not in sys_cfg

    leg = next(e for e in scenario.routing.routing_table_for_report()["9990"] if e["SYSTEM"] == "MASTER-A")
    assert leg["ACTIVE"] is True
    assert leg["TO_TYPE"] == "NONE"


def test_options_merge_static_tgs_from_all_connected_peers() -> None:
    """Last peer RPTO must not drop other hotspots' static TG bridges (inject proxy)."""
    scenario = DeterministicScenario()
    add_openbridge_system(scenario.config)
    scenario._wire_protocols_from_config()
    scenario.routing._get_protocols = lambda: scenario.protocols  # noqa: SLF001
    master = scenario.config["SYSTEMS"]["MASTER-A"]
    master["OPTIONS"] = "TS2=8730444;TIMER=300"
    proto = scenario.protocols["MASTER-A"]
    proto._peers = {
        bytes_4(730039101): {
            "CONNECTION": "YES",
            "OPTIONS": b"TS2=730444;TIMER=300",
        },
        bytes_4(730266501): {
            "CONNECTION": "YES",
            "OPTIONS": b"TS2=8730444;TIMER=300",
        },
    }

    scenario.routing.options_config_for_system("MASTER-A")

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert "730444" in sys_cfg["TS2_STATIC"]
    assert "8730444" in sys_cfg["TS2_STATIC"]
    bridges = scenario.routing.routing_table_for_report()
    assert "730444" in bridges
    assert "8730444" in bridges
    leg_730444 = next(e for e in bridges["730444"] if e["SYSTEM"] == "MASTER-A" and e["TS"] == 2)
    assert leg_730444["ACTIVE"] is True


def test_rule_timer_keeps_bridge_with_active_obp_none_leg() -> None:
    """Static TG bridges must survive rule_timer when OBP uses TO_TYPE NONE (ensure_dynamic_relay)."""
    scenario = DeterministicScenario()
    add_openbridge_system(scenario.config)
    scenario._wire_protocols_from_config()
    scenario.routing.ensure_dynamic_relay(bytes_3(730444), "MASTER-A", 2, 300.0)
    bridges = scenario.routing.routing_table_for_report()
    for entry in bridges["730444"]:
        if entry["SYSTEM"] == "OBP-CL":
            entry["ACTIVE"] = True
            entry["TO_TYPE"] = "NONE"

    scenario.routing.rule_timer_loop()

    assert "730444" in scenario.routing.routing_table_for_report()


def test_options_applies_valid_static_tg_once() -> None:
    scenario = _master_with_options("TS2=52090;TIMER=10")
    scenario.routing.options_config_for_system("MASTER-A")

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg["TS2_STATIC"] == "52090"
    assert "52090" in scenario.routing.routing_table_for_report()
    fp = sys_cfg.get("_options_static_apply_fp")
    assert fp == "|52090|1"

    scenario.routing.options_config_for_system("MASTER-A")
    assert scenario.config["SYSTEMS"]["MASTER-A"].get("_options_static_apply_fp") == fp
