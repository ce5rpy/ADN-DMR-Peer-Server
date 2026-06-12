# ADN DMR Peer Server - tests infrastructure parrot config
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
