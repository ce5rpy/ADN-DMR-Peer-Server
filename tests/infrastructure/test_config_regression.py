"""Regression: configs that must keep loading after proxy integration."""

from __future__ import annotations

from adn_server.infrastructure import YamlConfigLoader


def test_adn_parrot_yaml_loads_without_proxy_block() -> None:
    loader = YamlConfigLoader("/opt/new-adn-server")
    config = loader.load("/opt/new-adn-server/adn-parrot.yaml")
    assert "PROXY" not in config or config.get("PROXY") == {}
    assert config["SYSTEMS"]["PARROT"]["MODE"] == "PEER"


def test_adn_server_yaml_loads_with_proxy() -> None:
    loader = YamlConfigLoader("/opt/new-adn-server")
    config = loader.load("/opt/new-adn-server/adn-server.yaml")
    assert config["PROXY"]["TARGET_SYSTEM"] == "SYSTEM"
    assert config["PROXY"]["LISTEN_PORT"] == 62031
