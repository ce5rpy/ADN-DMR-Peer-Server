# ADN DMR Peer Server - keys JSON store
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

"""Load/save keys from JSON (legacy utils.load_json/save_json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...application.ports import KeysStore


class JsonKeysStore(KeysStore):
    """Persist keys as JSON."""

    def load(self, path: str) -> dict[str, Any]:
        """Load keys from JSON file."""
        p = Path(path)
        if not p.is_file():
            return {}
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, path: str, keys: dict[str, Any]) -> None:
        """Save keys to JSON file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2)
