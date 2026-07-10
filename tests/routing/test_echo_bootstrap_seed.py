# ADN DMR Peer Server - tests routing echo bootstrap seed
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

"""Regression: echo bridge 9990 must route to ECHO (bootstrap seed + VHEAD ON arm)."""

from __future__ import annotations

from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.routing.test_echo_subscription_reset import _echo_scenario_config

from adn_server.application.subscription.echo_seed import seed_echo_routing_table


def _prod_like_config() -> dict:
    config = _echo_scenario_config()
    sys_cfg = config["SYSTEMS"].pop("SYSTEM-82")
    sys_cfg["TS2_STATIC"] = ""
    config["SYSTEMS"]["SYSTEM"] = sys_cfg
    return config


def test_echo_routing_missing_without_echo_store_seed() -> None:
    scenario = DeterministicScenario(config=_prod_like_config(), routing_table={})
    scenario.routing.apply_startup_subscriptions()

    base = PacketSpec(dst_id=9990, stream_id=0xABCDEF01, slot=2)
    scenario.inject_hbp("SYSTEM", DeterministicScenario.voice_head_spec(base))

    assert scenario.capture.for_system("ECHO") == []


def test_echo_routing_works_after_echo_seed_on_vhead() -> None:
    config = _prod_like_config()
    scenario = DeterministicScenario(config=config, routing_table=seed_echo_routing_table(config))
    scenario.routing.apply_startup_subscriptions()

    base = PacketSpec(dst_id=9990, stream_id=0xABCDEF02, slot=2)
    scenario.inject_hbp("SYSTEM", DeterministicScenario.voice_head_spec(base))
    scenario.inject_hbp(
        "SYSTEM",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_forwarded(scenario, "ECHO", count=2, dst_id=9990)
