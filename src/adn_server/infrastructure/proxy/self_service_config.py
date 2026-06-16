# ADN DMR Peer Server - infrastructure proxy self service config
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

"""SELF_SERVICE block from config (same keys as adn-monitor / adn-proxy)."""

from __future__ import annotations

from typing import Any


def self_service_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Resolved self-service settings; disabled when block missing or USE_SELFSERVICE false."""
    block = config.get("SELF_SERVICE") or {}
    if not isinstance(block, dict):
        block = {}
    enabled = bool(block.get("USE_SELFSERVICE", block.get("ENABLED", False)))
    return {
        "enabled": enabled,
        "db_server": str(block.get("DB_SERVER", "localhost")),
        "db_username": str(block.get("DB_USERNAME", "")),
        "db_password": str(block.get("DB_PASSWORD", "")),
        "db_name": str(block.get("DB_NAME", "")),
        "db_port": int(block.get("DB_PORT", 3306)),
        "pbkdf2_salt": str(block.get("PBKDF2_SALT", "ADN")),
        "pbkdf2_iterations": int(block.get("PBKDF2_ITERATIONS", 2000)),
    }
