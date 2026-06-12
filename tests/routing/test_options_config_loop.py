# ADN DMR Peer Server - tests routing options config loop
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
###############################################################################
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
###############################################################################

"""OPTIONS refresh paths (RPTO, startup, connected peer — no 26s loop, V2-P2-016)."""

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario


def test_options_config_for_system_applies_static_tg_from_yaml_options() -> None:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = "TS2=52090;TIMER=10"
    config["SYSTEMS"]["MASTER-A"]["TS1_STATIC"] = ""
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.routing.options_config_for_system("MASTER-A")

    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    assert sys_cfg["TS2_STATIC"] == "52090"
    assert "52090" in scenario.routing.routing_table_for_report()


def test_options_config_for_system_skips_master_without_options() -> None:
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"].pop("OPTIONS", None)
    config["SYSTEMS"]["MASTER-B"]["OPTIONS"] = "TS2=91;TIMER=10"
    config["SYSTEMS"]["MASTER-B"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.routing.options_config_for_system("MASTER-A")
    scenario.routing.options_config_for_system("MASTER-B")

    assert scenario.config["SYSTEMS"]["MASTER-A"].get("TS2_STATIC", "") == ""
    assert scenario.config["SYSTEMS"]["MASTER-B"]["TS2_STATIC"] == "91"


def test_apply_startup_runs_options_config_for_each_master() -> None:
    """Startup/reload path: YAML OPTIONS without TS*_STATIC still materializes bridges."""
    config = DeterministicScenario().config
    config["SYSTEMS"]["MASTER-A"]["OPTIONS"] = "TS2=52090;TIMER=10"
    config["SYSTEMS"]["MASTER-A"]["TS1_STATIC"] = ""
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = ""
    scenario = DeterministicScenario(config=config)

    scenario.routing.apply_startup_subscriptions()

    assert scenario.config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] == "52090"
    assert "52090" in scenario.routing.routing_table_for_report()
