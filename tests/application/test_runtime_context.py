# ADN DMR Peer Server - tests application runtime context
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

"""RuntimeContext holder and ConfigProxy."""

from __future__ import annotations

from adn_server.application.runtime_context import (
    ConfigProxy,
    RuntimeContext,
    RuntimeContextHolder,
    prepare_reload_config,
    swap_runtime_config,
)


def test_config_proxy_reads_swapped_config() -> None:
    holder = RuntimeContextHolder(RuntimeContext(config={"GLOBAL": {"A": 1}}))
    proxy = ConfigProxy(holder)

    assert proxy["GLOBAL"]["A"] == 1

    swap_runtime_config(holder, {"GLOBAL": {"A": 2}})

    assert proxy["GLOBAL"]["A"] == 2


def test_config_proxy_mutations_visible_after_swap() -> None:
    holder = RuntimeContextHolder(RuntimeContext(config={"_SUB_IDS": {"1": "A"}}))
    proxy = ConfigProxy(holder)
    proxy["_SUB_IDS"]["2"] = "B"

    new_config = prepare_reload_config(holder)
    swap_runtime_config(holder, new_config)

    assert proxy["_SUB_IDS"]["2"] == "B"


def test_prepare_reload_config_shares_sub_map() -> None:
    sub_map = {"k": (1, 2, 3.0)}
    holder = RuntimeContextHolder(RuntimeContext(config={"_SUB_MAP": sub_map, "SYSTEMS": {}}))

    new_config = prepare_reload_config(holder)

    assert new_config["_SUB_MAP"] is sub_map
    assert new_config is not holder.get().config


def test_failed_reload_leaves_holder_unchanged() -> None:
    live = {"GLOBAL": {"X": 1}, "SYSTEMS": {}}
    holder = RuntimeContextHolder(RuntimeContext(config=live))
    proxy = ConfigProxy(holder)

    new_config = prepare_reload_config(holder)
    new_config["GLOBAL"]["X"] = 99

    # Simulate aborted reload: do not swap.
    assert holder.get().config["GLOBAL"]["X"] == 1
    assert proxy["GLOBAL"]["X"] == 1


def test_swap_runtime_config_preserves_config_path() -> None:
    holder = RuntimeContextHolder(RuntimeContext(config={}, config_path="/etc/adn-server.yaml"))

    swap_runtime_config(holder, {"GLOBAL": {}}, config_path="/etc/adn-server.yaml")

    assert holder.get().config_path == "/etc/adn-server.yaml"


def test_swap_runtime_config_preserves_subscription_store() -> None:
    store = object()
    holder = RuntimeContextHolder(RuntimeContext(config={"GLOBAL": {}}, subscription_store=store))

    swap_runtime_config(holder, {"GLOBAL": {"X": 1}})

    assert holder.get().subscription_store is store
