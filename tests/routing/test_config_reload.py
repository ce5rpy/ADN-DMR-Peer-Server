"""Config reload merge preserves runtime MASTER state."""

from __future__ import annotations

from adn_server.infrastructure.config_reload import merge_system_config


def test_merge_system_config_preserves_peers_and_static_tgs() -> None:
    old = {
        "MODE": "MASTER",
        "ENABLED": True,
        "IP": "127.0.0.1",
        "PORT": 62031,
        "PEERS": {"1001": {"IP": "10.0.0.1"}},
        "OPTIONS": "TS2=52090;TIMER=10",
        "TS1_STATIC": "91",
        "TS2_STATIC": "52090",
        "DEFAULT_UA_TIMER": 10,
        "_options_static_apply_fp": "52090|10",
    }
    new = {
        "MODE": "MASTER",
        "ENABLED": True,
        "IP": "127.0.0.1",
        "PORT": 62031,
        "GROUP_HANGTIME": 3,
        "TS1_STATIC": "",
        "TS2_STATIC": "",
    }

    merged = merge_system_config(old, new)

    assert merged["PEERS"] == old["PEERS"]
    assert merged["OPTIONS"] == old["OPTIONS"]
    assert merged["TS1_STATIC"] == old["TS1_STATIC"]
    assert merged["TS2_STATIC"] == old["TS2_STATIC"]
    assert merged["_options_static_apply_fp"] == old["_options_static_apply_fp"]
    assert merged["GROUP_HANGTIME"] == 3


def test_merge_new_master_keeps_yaml_static_tg() -> None:
    """New MASTER on reload keeps YAML static lists (apply_startup_subscriptions materializes them)."""
    new = {
        "MODE": "MASTER",
        "ENABLED": True,
        "IP": "127.0.0.1",
        "PORT": 62032,
        "TS2_STATIC": "52090",
        "DEFAULT_UA_TIMER": 10,
    }

    merged = merge_system_config({}, new)

    assert merged["TS2_STATIC"] == "52090"
