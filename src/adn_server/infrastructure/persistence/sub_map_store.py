# ADN DMR Peer Server - SUB_MAP persistence
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

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
