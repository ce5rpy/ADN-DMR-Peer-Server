"""Shared deterministic scenario builders for domain tests."""

from __future__ import annotations

from typing import Any

from adn_server.application.talker_alias_use_cases import TalkerAliasUseCases
from adn_server.infrastructure.talker_alias_emblc import default_ta_emblc_encoder

from .deterministic import (
    DeterministicScenario,
    active_bridge,
    add_openbridge_system,
)


def obp_bridge_scenario(*obp_names: str, tg: int = 52090) -> DeterministicScenario:
    entries = [(name, 1) for name in obp_names] + [("MASTER-A", 2)]
    bridges = active_bridge(tg, tuple(entries))
    config = DeterministicScenario().config
    for name in obp_names:
        add_openbridge_system(config, name)
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = str(tg)
    return DeterministicScenario(config=config, bridges=bridges)


def talker_alias_config() -> dict[str, Any]:
    config = DeterministicScenario().config
    config["GLOBAL"]["TALKER_ALIAS"] = True
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "inject"
    config["GLOBAL"]["TALKER_ALIAS_FORMAT"] = "{callsign} {fname}"
    rid = 3120001
    config["_SUB_PROFILES"] = {
        rid: {"callsign": "CE5RPY", "fname": "Rodrigo", "surname": "Perez"},
    }
    config["_SUB_IDS"] = {rid: "CE5RPY"}
    return config


def make_talker_alias_use_cases(config: dict[str, Any]) -> TalkerAliasUseCases:
    """Talker Alias use cases with production embedded-LC encoder (test harness)."""
    return TalkerAliasUseCases(config, ta_emblc_encoder=default_ta_emblc_encoder)
