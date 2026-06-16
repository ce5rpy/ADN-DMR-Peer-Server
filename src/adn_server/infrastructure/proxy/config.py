# ADN DMR Peer Server - infrastructure proxy config
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

"""PROXY runtime settings from config dict (infrastructure; no business rules)."""

from __future__ import annotations

from typing import Any


def apply_proxy_env_overrides(config: dict[str, Any]) -> None:
    """Apply ADN_PROXY_* environment overrides (design §5.6)."""
    import os

    proxy = config.setdefault("PROXY", {})
    if os.environ.get("ADN_PROXY_DEBUG", "").strip() in ("1", "true", "TRUE", "yes", "YES"):
        proxy["DEBUG"] = True
    listen_port = os.environ.get("ADN_PROXY_LISTENPORT", "").strip()
    if listen_port:
        proxy["LISTEN_PORT"] = int(listen_port)
    if os.environ.get("ADN_PROXY_IPV6", "").strip() in ("1", "true", "TRUE", "yes", "YES"):
        proxy["LISTEN_IP"] = "::"


def proxy_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Resolved PROXY runtime settings with defaults."""
    proxy = config.get("PROXY", {})
    black_list = proxy.get("BLACK_LIST") or []
    if not isinstance(black_list, list):
        black_list = []
    ip_black_list = proxy.get("IP_BLACK_LIST") or {}
    if not isinstance(ip_black_list, dict):
        ip_black_list = {}
    return {
        "listen_port": int(proxy.get("LISTEN_PORT", 62031)),
        "listen_ip": str(proxy.get("LISTEN_IP") or ""),
        "target_system": str(proxy.get("TARGET_SYSTEM") or ""),
        "timeout": float(proxy.get("TIMEOUT", 30)),
        "debug": bool(proxy.get("DEBUG")),
        "client_info": bool(proxy.get("CLIENT_INFO", True)),
        "black_list": tuple(int(x) for x in black_list),
        "ip_black_list": {str(k): float(v) for k, v in ip_black_list.items()},
        "stats": bool(proxy.get("STATS")),
    }
