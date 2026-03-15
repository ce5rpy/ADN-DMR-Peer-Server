# ADN DMR Peer Server - bridge router implementation
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
# Derived from ADN DMR Server / FreeDMR  / HBlink. Original license:
###############################################################################
# Copyright (C) 2020 Simon Adlem, G7RZU <g7rzu@gb7fr.org.uk>
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS <n0mjs@me.com>
#
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

"""In-memory BRIDGES and ACL check (legacy acl_check)."""

from __future__ import annotations

from typing import Any

from ..application.ports import BridgeRouter


def _int_id(val: bytes | int) -> int:
    if isinstance(val, int):
        return val
    if len(val) >= 4:
        return int.from_bytes(val[:4], "big")
    if len(val) == 3:
        return int.from_bytes(val, "big")
    return 0


class InMemoryBridgeRouter(BridgeRouter):
    """Holds BRIDGES dict; implements acl_check like legacy."""

    def __init__(self) -> None:
        self._bridges: dict[str, list[dict[str, Any]]] = {}

    def get_bridges(self) -> dict[str, list[dict[str, Any]]]:
        return self._bridges

    def set_bridges(self, bridges: dict[str, list[dict[str, Any]]]) -> None:
        self._bridges = bridges

    def acl_check(self, id_bytes_or_int: bytes | int, acl: tuple[bool, list[tuple[int, int]]]) -> bool:
        """Legacy acl_check: (action, ranges). If id in any range return action else not action."""
        action, ranges = acl
        i = _int_id(id_bytes_or_int)
        for lo, hi in ranges:
            if lo <= i <= hi:
                return action
        return not action
