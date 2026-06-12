# ADN DMR Peer Server - application proxy deployment
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

"""Proxy deployment policy from config dict (no I/O; used at startup/reload)."""

from __future__ import annotations

from typing import Any


def proxy_target_system(config: dict[str, Any]) -> str | None:
    proxy = config.get("PROXY", {})
    target = proxy.get("TARGET_SYSTEM")
    return str(target) if target else None


def config_has_enabled_master(config: dict[str, Any]) -> bool:
    """True when config defines at least one enabled MASTER (adn-server, not parrot-only)."""
    systems = config.get("SYSTEMS", {})
    if not isinstance(systems, dict):
        return False
    return any(
        isinstance(cfg, dict) and cfg.get("ENABLED", True) and cfg.get("MODE") == "MASTER"
        for cfg in systems.values()
    )


def is_proxy_inject_only(config: dict[str, Any], system_name: str) -> bool:
    target = proxy_target_system(config)
    return target is not None and target == system_name


def normalize_proxy_target(config: dict[str, Any]) -> None:
    """Strip direct UDP bind fields from inject-only proxy target (D-23)."""
    target = proxy_target_system(config)
    if not target:
        return
    sys_cfg = config.get("SYSTEMS", {}).get(target)
    if not isinstance(sys_cfg, dict):
        return
    port = sys_cfg.pop("PORT", None)
    sys_cfg.pop("IP", None)
    if port is not None:
        sys_cfg["_REPORT_BASE_PORT"] = int(port)
    else:
        sys_cfg.setdefault("_REPORT_BASE_PORT", 56400)
