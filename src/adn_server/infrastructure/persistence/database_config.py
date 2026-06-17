# ADN DMR Peer Server - infrastructure persistence database config
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

"""DATABASE block from config (MariaDB for dynamic TG persistence)."""

from __future__ import annotations

from typing import Any


def _block(config: dict[str, Any], key: str) -> dict[str, Any]:
    raw = config.get(key) or {}
    return raw if isinstance(raw, dict) else {}


def database_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Resolved MariaDB settings from ``DATABASE``."""
    block = _block(config, "DATABASE")
    return {
        "db_server": str(block.get("DB_SERVER", "localhost")),
        "db_username": str(block.get("DB_USERNAME", "")),
        "db_password": str(block.get("DB_PASSWORD", "")),
        "db_name": str(block.get("DB_NAME", "")),
        "db_port": int(block.get("DB_PORT", 3306)),
    }
