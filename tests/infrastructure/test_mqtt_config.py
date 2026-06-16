# ADN DMR Peer Server - tests infrastructure mqtt config
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

"""Tests for optional REPORTS.MQTT configuration."""

from __future__ import annotations

from adn_server.infrastructure.config_validator import validate_config
from adn_server.infrastructure.twisted_adapters.report.mqtt_config import (
    mqtt_settings_from_config,
    parse_mqtt_broker,
)

from tests.conftest import minimal_valid_config


def test_mqtt_disabled_by_default():
    config = {"REPORTS": {"REPORT": True}, "GLOBAL": {"SERVER_ID": 73010}}
    assert mqtt_settings_from_config(config) is None


def test_mqtt_disabled_when_url_without_enabled():
    config = {
        "REPORTS": {"MQTT_URL": "mqtt://127.0.0.1:1883"},
        "GLOBAL": {"SERVER_ID": 73010},
    }
    assert mqtt_settings_from_config(config) is None


def test_mqtt_enabled_with_nested_block():
    config = {
        "GLOBAL": {"SERVER_ID": 73010},
        "REPORTS": {
            "MQTT": {
                "ENABLED": True,
                "URL": "mqtt://broker.example:1883",
                "TOPIC_PREFIX": "lab/adn",
                "QOS": 1,
            }
        },
    }
    settings = mqtt_settings_from_config(config)
    assert settings is not None
    assert settings.broker.display_url == "mqtt://broker.example:1883"
    assert settings.topic_prefix == "lab/adn"
    assert settings.qos == 1


def test_mqtt_default_topic_prefix_from_server_id():
    config = {
        "GLOBAL": {"SERVER_ID": 99999},
        "REPORTS": {"MQTT": {"ENABLED": True, "URL": "mqtt://127.0.0.1:1883"}},
    }
    settings = mqtt_settings_from_config(config)
    assert settings is not None
    assert settings.topic_prefix == "adn/99999"


def test_validate_mqtt_enabled_requires_url():
    config = minimal_valid_config(
        REPORTS={"MQTT": {"ENABLED": True}},
    )
    try:
        validate_config(config)
        raised = False
    except Exception as exc:
        raised = True
        assert "REPORTS.MQTT.URL" in str(exc)
    assert raised


def test_mqtt_credentials_from_url():
    config = {
        "GLOBAL": {"SERVER_ID": 1},
        "REPORTS": {
            "MQTT": {
                "ENABLED": True,
                "URL": "mqtt://reportuser:secr%40et@mqtt.example:1883",
            }
        },
    }
    settings = mqtt_settings_from_config(config)
    assert settings is not None
    assert settings.username == "reportuser"
    assert settings.password == "secr@et"
    assert settings.broker.host == "mqtt.example"
    assert "reportuser" not in settings.broker.display_url


def test_mqtt_yaml_credentials_override_url():
    config = {
        "GLOBAL": {"SERVER_ID": 1},
        "REPORTS": {
            "MQTT": {
                "ENABLED": True,
                "URL": "mqtt://urluser:urlpass@127.0.0.1:1883",
                "USERNAME": "yamluser",
                "PASSWORD": "yamlpass",
            }
        },
    }
    settings = mqtt_settings_from_config(config)
    assert settings is not None
    assert settings.username == "yamluser"
    assert settings.password == "yamlpass"


def test_mqtt_client_id_derived_from_server_id():
    config = {
        "GLOBAL": {"SERVER_ID": 7302},
        "REPORTS": {"MQTT": {"ENABLED": True, "URL": "mqtt://127.0.0.1:1883"}},
    }
    settings = mqtt_settings_from_config(config)
    assert settings is not None
    assert settings.client_id.startswith("adn-server-7302-")
    suffix = settings.client_id.removeprefix("adn-server-7302-")
    assert len(suffix) == 8
    assert all(c in "0123456789abcdef" for c in suffix)


def test_mqtt_topic_prefix_from_normalized_server_id_bytes():
    """After config_normalizer, SERVER_ID is 4-byte big-endian (7302 -> b'\\x00\\x00\\x1c\\x86')."""
    config = {
        "GLOBAL": {"SERVER_ID": (7302).to_bytes(4, "big")},
        "REPORTS": {"MQTT": {"ENABLED": True, "URL": "mqtt://127.0.0.1:1883"}},
    }
    settings = mqtt_settings_from_config(config)
    assert settings is not None
    assert settings.topic_prefix == "adn/7302"
    assert settings.client_id.startswith("adn-server-7302-")


def test_parse_mqtts_default_port():
    broker, user, passwd = parse_mqtt_broker("mqtts://secure.example")
    assert broker.port == 8883
    assert broker.use_tls is True
    assert user is None and passwd is None
