# ADN DMR Peer Server - infrastructure proxy obp config
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

"""OBP_PROXY runtime settings from config dict (infrastructure; no business rules)."""

from __future__ import annotations

from typing import Any

from adn_server.application.proxy.deployment import obp_proxy_bind_legacy_ports, obp_proxy_enabled


def obp_proxy_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Resolved OBP_PROXY runtime settings with defaults (block may be absent)."""
    block = config.get("OBP_PROXY", {})
    if not isinstance(block, dict):
        block = {}
    return {
        "enabled": obp_proxy_enabled(config),
        "listen_port": int(block.get("LISTEN_PORT", 62032)),
        "listen_ip": str(block.get("LISTEN_IP") or ""),
        "bind_legacy_ports": obp_proxy_bind_legacy_ports(config),
        "debug": bool(block.get("DEBUG")),
    }
