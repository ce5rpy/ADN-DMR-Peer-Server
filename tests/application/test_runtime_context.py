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
