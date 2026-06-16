# ADN DMR Peer Server - tests conftest
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

"""Shared test fixtures."""

from __future__ import annotations

from typing import Any


def minimal_valid_config(**overrides: Any) -> dict[str, Any]:
    """Minimal config dict that passes validate_config (integrated proxy required)."""
    config: dict[str, Any] = {
        "GLOBAL": {"SERVER_ID": 1},
        "REPORTS": {"REPORT": False},
        "SYSTEMS": {
            "HOTSPOT": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 8,
            }
        },
        "PROXY": {
            "LISTEN_PORT": 62031,
            "TARGET_SYSTEM": "HOTSPOT",
            "TIMEOUT": 30,
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    return config
