# ADN DMR Peer Server - application subscription echo seed
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

"""Initial BRIDGES snapshot for the ECHO parrot system (bootstrap only)."""

from __future__ import annotations

import time
from typing import Any

from adn_server.domain import bytes_3


def seed_echo_routing_table(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Initial BRIDGES for ECHO system (legacy make_bridges 9990 + MASTER expansion)."""
    now = time.time()
    timeout_sec = 2 * 60
    tgid_b = bytes_3(9990)
    bridges: dict[str, list[dict[str, Any]]] = {
        "9990": [
            {
                "SYSTEM": "ECHO",
                "TS": 2,
                "TGID": tgid_b,
                "ACTIVE": True,
                "TIMEOUT": timeout_sec,
                "TO_TYPE": "NONE",
                "ON": [],
                "OFF": [],
                "RESET": [],
                "TIMER": now + timeout_sec,
            }
        ]
    }
    systems_cfg = config.get("SYSTEMS", {})
    for _system, sys_cfg in systems_cfg.items():
        if _system == "ECHO":
            continue
        if sys_cfg.get("MODE") != "MASTER":
            continue
        _tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
        bridges["9990"].append(
            {
                "SYSTEM": _system,
                "TS": 1,
                "TGID": tgid_b,
                "ACTIVE": False,
                "TIMEOUT": _tmout * 60,
                "TO_TYPE": "ON",
                "OFF": [],
                "ON": [tgid_b],
                "RESET": [],
                "TIMER": now,
            }
        )
        bridges["9990"].append(
            {
                "SYSTEM": _system,
                "TS": 2,
                "TGID": tgid_b,
                "ACTIVE": False,
                "TIMEOUT": _tmout * 60,
                "TO_TYPE": "ON",
                "OFF": [],
                "ON": [tgid_b],
                "RESET": [],
                "TIMER": now,
            }
        )
    return bridges
