# ADN DMR Peer Server - application subscription trigger bytes
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

"""Normalize legacy BRIDGES ON/OFF/RESET lists to bytes tuples."""

from __future__ import annotations

from typing import Any

from adn_server.domain import bytes_3, int_id


def trigger_bytes_tuple(items: Any) -> tuple[bytes, ...]:
    if not items:
        return ()
    out: list[bytes] = []
    for item in items:
        if isinstance(item, bytes):
            out.append(item[:3].ljust(3, b"\x00") if len(item) >= 3 else bytes_3(int_id(item)))
        elif isinstance(item, int):
            out.append(bytes_3(item))
    return tuple(out)


def dst_in_triggers(dst_id_b: bytes, dst_group: int, triggers: tuple[bytes, ...]) -> bool:
    if dst_id_b in triggers:
        return True
    return any(int_id(item) == dst_group for item in triggers)
