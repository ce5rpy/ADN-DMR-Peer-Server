"""Minimal adn-parrot.yaml validation."""

from __future__ import annotations

from adn_server.infrastructure.config_validator import validate_config


MINIMAL_PARROT = {
    "GLOBAL": {"SERVER_ID": 9990},
    "LOGGER": {"LOG_FILE": "/var/log/adn-server/parrot.log"},
    "SYSTEMS": {
        "PARROT": {
            "MODE": "PEER",
            "IP": "127.0.0.1",
            "PORT": 54915,
            "MASTER_IP": "127.0.0.1",
            "MASTER_PORT": 54917,
            "PASSPHRASE": "secret",
            "RADIO_ID": 9990,
            "CALLSIGN": "ECHO",
            "OPTIONS": "TS2=9990;",
        },
    },
}


def test_minimal_parrot_config_validates_without_proxy() -> None:
    validate_config(MINIMAL_PARROT)


def test_minimal_parrot_has_no_reports_or_aliases() -> None:
    assert "REPORTS" not in MINIMAL_PARROT
    assert "ALIASES" not in MINIMAL_PARROT
    assert "PROXY" not in MINIMAL_PARROT
