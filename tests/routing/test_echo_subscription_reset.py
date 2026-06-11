"""ECHO / parrot bridge leg restore after BRIDGERESET (regression for production outage)."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import DeterministicScenario, PacketSpec, minimal_config

from adn_server.domain import ID_MAX, PEER_MAX
from adn_server.infrastructure.config_loader import acl_build
from adn_server.infrastructure.bootstrap.peer_server import _seed_echo_routing_table


def _echo_scenario_config() -> dict:
    config = minimal_config(("SYSTEM-82",))
    config["SYSTEMS"]["ECHO"] = {
        "MODE": "MASTER",
        "ENABLED": True,
        "REPEAT": True,
        "MAX_PEERS": 1,
        "IP": "127.0.0.1",
        "PORT": 54917,
        "PASSPHRASE": b"passw0rd",
        "GROUP_HANGTIME": 5,
        "USE_ACL": True,
        "REG_ACL": "DENY:1",
        "SUB_ACL": "DENY:1",
        "TGID_TS1_ACL": "DENY:ALL",
        "TGID_TS2_ACL": "PERMIT:9990",
        "DEFAULT_UA_TIMER": 1,
        "SINGLE_MODE": True,
        "VOICE_IDENT": False,
        "TS1_STATIC": "",
        "TS2_STATIC": "9990",
        "DEFAULT_REFLECTOR": 0,
        "GENERATOR": 0,
        "ALLOW_UNREG_ID": True,
        "PEERS": {},
    }
    config["SYSTEMS"]["SYSTEM-82"]["TS2_STATIC"] = ""
    echo = config["SYSTEMS"]["ECHO"]
    echo["REG_ACL"] = acl_build(str(echo["REG_ACL"]), PEER_MAX)
    echo["SUB_ACL"] = acl_build(str(echo["SUB_ACL"]), ID_MAX)
    echo["TG1_ACL"] = acl_build(str(echo["TGID_TS1_ACL"]), ID_MAX)
    echo["TG2_ACL"] = acl_build(str(echo["TGID_TS2_ACL"]), ID_MAX)
    return config


def _bridges_after_bridgereset(config: dict) -> dict:
    bridges = _seed_echo_routing_table(config)
    for entry in bridges["9990"]:
        if entry["SYSTEM"] == "ECHO":
            entry["ACTIVE"] = False
            entry["TO_TYPE"] = "ON"
    for entry in bridges["9990"]:
        if entry["SYSTEM"] == "SYSTEM-82":
            entry["ACTIVE"] = True
            entry["TO_TYPE"] = "ON"
    return bridges


def test_bridge_reset_restores_echo_leg_with_use_acl() -> None:
    """BRIDGERESET must restore ECHO service leg when USE_ACL and TG2_ACL are processed."""
    config = _echo_scenario_config()
    config["SYSTEMS"]["ECHO"]["_reset"] = True
    bridges = _bridges_after_bridgereset(config)
    scenario = DeterministicScenario(config=config, routing_table=bridges)

    scenario.routing.subscription_reset_loop()

    echo_leg = next(e for e in scenario.routing.routing_table_for_report()["9990"] if e["SYSTEM"] == "ECHO")
    assert echo_leg["ACTIVE"] is True
    assert echo_leg["TO_TYPE"] == "NONE"


def test_options_config_restores_echo_after_bridgereset() -> None:
    """Peer RPTO (options_config_for_system) re-enables ECHO leg after BRIDGERESET."""
    config = _echo_scenario_config()
    echo_cfg = config["SYSTEMS"]["ECHO"]
    echo_cfg["OPTIONS"] = "TS2=9990;"
    bridges = _bridges_after_bridgereset(config)
    scenario = DeterministicScenario(config=config, routing_table=bridges)

    scenario.routing.options_config_for_system("ECHO")

    echo_leg = next(e for e in scenario.routing.routing_table_for_report()["9990"] if e["SYSTEM"] == "ECHO")
    assert echo_leg["ACTIVE"] is True
    assert echo_leg["TO_TYPE"] == "NONE"


@pytest.mark.behavior
def test_echo_voice_forwards_after_bridgereset_and_options() -> None:
    """Regression: voice on TG 9990 reaches ECHO master after reset + RPTO restore."""
    config = _echo_scenario_config()
    echo_cfg = config["SYSTEMS"]["ECHO"]
    echo_cfg["OPTIONS"] = "TS2=9990;"
    bridges = _bridges_after_bridgereset(config)
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.routing.options_config_for_system("ECHO")

    base = PacketSpec(dst_id=9990, stream_id=0xDEADBEEF, slot=2)
    scenario.inject_hbp("SYSTEM-82", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "SYSTEM-82",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "ECHO", count=2, dst_id=9990)


def test_bridge_reset_with_yaml_tgid_ts_acl_only() -> None:
    """Restore reads TG2_ACL tuple (as after process_acls), not TGID_TS2_ACL YAML string."""
    config = _echo_scenario_config()
    echo = config["SYSTEMS"]["ECHO"]
    echo["TG1_ACL"] = acl_build(str(echo["TGID_TS1_ACL"]), ID_MAX)
    echo["TG2_ACL"] = acl_build(str(echo["TGID_TS2_ACL"]), ID_MAX)
    echo["_reset"] = True
    bridges = _bridges_after_bridgereset(config)
    scenario = DeterministicScenario(config=config, routing_table=bridges)

    scenario.routing.subscription_reset_loop()

    echo_leg = next(e for e in scenario.routing.routing_table_for_report()["9990"] if e["SYSTEM"] == "ECHO")
    assert echo_leg["ACTIVE"] is True
    assert echo_leg["TO_TYPE"] == "NONE"


def test_bridge_reset_acl_uses_processed_tg2_acl_not_yaml_string() -> None:
    """_restore must not read raw TGID_TS2_ACL strings (TypeError in acl_check)."""
    config = _echo_scenario_config()
    echo_cfg = config["SYSTEMS"]["ECHO"]
    echo_cfg["TGID_TS2_ACL"] = "PERMIT:9990"
    echo_cfg["TG2_ACL"] = acl_build("PERMIT:9990", 16776415)
    echo_cfg["_reset"] = True
    bridges = _bridges_after_bridgereset(config)
    scenario = DeterministicScenario(config=config, routing_table=bridges)

    scenario.routing.subscription_reset_loop()

    echo_leg = next(e for e in scenario.routing.routing_table_for_report()["9990"] if e["SYSTEM"] == "ECHO")
    assert echo_leg["ACTIVE"] is True
