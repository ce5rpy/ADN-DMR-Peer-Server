"""PROXY configuration validation (Phase 3)."""

from __future__ import annotations

import logging

import pytest

from adn_server.application.proxy.deployment import (
    is_proxy_inject_only,
    normalize_proxy_target,
)
from adn_server.domain.errors import ConfigError
from adn_server.infrastructure.config_normalizer import expand_generator
from adn_server.infrastructure.config_validator import validate_config
from adn_server.infrastructure.proxy.config import apply_proxy_env_overrides

from tests.conftest import minimal_valid_config


def test_proxy_section_required_when_master_present() -> None:
    with pytest.raises(ConfigError) as exc:
        validate_config({
            "GLOBAL": {"SERVER_ID": 1},
            "SYSTEMS": {"HOTSPOT": {"MODE": "MASTER", "ENABLED": True, "MAX_PEERS": 1}},
        })
    assert "PROXY" in str(exc.value)


def test_parrot_config_without_proxy_is_valid() -> None:
    validate_config({
        "GLOBAL": {"SERVER_ID": 9990},
        "SYSTEMS": {"PARROT": {"MODE": "PEER", "ENABLED": True, "PORT": 54915}},
    })


def test_proxy_enabled_key_rejected() -> None:
    config = minimal_valid_config()
    config["PROXY"]["ENABLED"] = False
    with pytest.raises(ConfigError) as exc:
        validate_config(config)
    assert "PROXY.ENABLED" in str(exc.value)


def test_proxy_enabled_requires_listen_port_and_target() -> None:
    config = minimal_valid_config()
    del config["PROXY"]["TARGET_SYSTEM"]
    with pytest.raises(ConfigError) as exc:
        validate_config(config)
    assert "TARGET_SYSTEM" in str(exc.value)


def test_proxy_target_rejects_port_and_generator() -> None:
    config = minimal_valid_config()
    config["SYSTEMS"]["HOTSPOT"]["PORT"] = 56400
    with pytest.raises(ConfigError) as exc:
        validate_config(config)
    assert "PORT" in str(exc.value)

    config = minimal_valid_config()
    config["SYSTEMS"]["HOTSPOT"]["GENERATOR"] = 102
    with pytest.raises(ConfigError) as exc:
        validate_config(config)
    assert "GENERATOR" in str(exc.value)


def test_proxy_rejects_deprecated_keys() -> None:
    config = minimal_valid_config()
    config["PROXY"]["DISPATCH"] = True
    with pytest.raises(ConfigError) as exc:
        validate_config(config)
    assert "DISPATCH" in str(exc.value)


def test_valid_minimal_proxy_config() -> None:
    validate_config(minimal_valid_config())


def test_normalize_proxy_target_strips_bind_fields() -> None:
    config = minimal_valid_config()
    config["SYSTEMS"]["HOTSPOT"]["PORT"] = 56400
    config["SYSTEMS"]["HOTSPOT"]["IP"] = "127.0.0.1"
    config["SYSTEMS"]["HOTSPOT"]["GENERATOR"] = 102
    normalize_proxy_target(config)
    target = config["SYSTEMS"]["HOTSPOT"]
    assert "PORT" not in target
    assert "IP" not in target
    assert target["_REPORT_BASE_PORT"] == 56400
    assert is_proxy_inject_only(config, "HOTSPOT")


def test_apply_proxy_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    config = minimal_valid_config()
    monkeypatch.setenv("ADN_PROXY_DEBUG", "1")
    monkeypatch.setenv("ADN_PROXY_LISTENPORT", "63000")
    monkeypatch.setenv("ADN_PROXY_IPV6", "1")
    apply_proxy_env_overrides(config)
    assert config["PROXY"]["DEBUG"] is True
    assert config["PROXY"]["LISTEN_PORT"] == 63000
    assert config["PROXY"]["LISTEN_IP"] == "::"


def test_expand_generator_skips_proxy_target() -> None:
    config = minimal_valid_config(
        PROXY={"LISTEN_PORT": 62031, "TARGET_SYSTEM": "HOTSPOT"},
        SYSTEMS={
            "HOTSPOT": {
                "MODE": "MASTER",
                "ENABLED": True,
                "PORT": 56400,
                "GENERATOR": 4,
                "MAX_PEERS": 8,
            }
        },
    )
    expand_generator(config, logging.getLogger("test"))
    assert "HOTSPOT-0" not in config["SYSTEMS"]
    assert "HOTSPOT" in config["SYSTEMS"]
