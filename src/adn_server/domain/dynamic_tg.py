# ADN DMR Peer Server - domain dynamic tg
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

"""Per-peer user-activated dynamic TG persistence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DynamicTgEntry:
    """One persisted dynamic TG row for a hotspot peer."""

    int_id: int
    system_name: str
    slot: int
    tgid: int
    single_mode: bool
    expires_at: float | None
    updated_at: float
    need_reload: bool = False


def is_persisted_dynamic_row(entry: DynamicTgEntry) -> bool:
    """True for real dynamic TG rows (exclude monitor reload control rows)."""
    if entry.need_reload:
        return False
    if int(entry.slot) == 0 and int(entry.tgid) == 0:
        return False
    return True
