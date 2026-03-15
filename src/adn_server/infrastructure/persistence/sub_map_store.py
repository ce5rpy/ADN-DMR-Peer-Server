# ADN DMR Peer Server - SUB_MAP persistence
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

"""Load/save SUB_MAP (pickle): bytes_3(peer) -> (callsign, slot, time)."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

from ...application.ports import SubMapStore


class PickleSubMapStore(SubMapStore):
    """Persist SUB_MAP as pickle (legacy compatible)."""

    def load(self, path: str) -> dict[bytes, tuple[str, int, float]]:
        """Load SUB_MAP from pickle file."""
        p = Path(path)
        if not p.is_file():
            return {}
        try:
            with open(p, "rb") as f:
                return pickle.load(f)
        except (pickle.PickleError, OSError):
            return {}

    def save(self, path: str, sub_map: dict[bytes, tuple[str, int, float]]) -> None:
        """Save SUB_MAP to pickle file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            pickle.dump(sub_map, f)
