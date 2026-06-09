"""Shared test fixtures."""

from __future__ import annotations

from typing import Any


def minimal_valid_config(**overrides: Any) -> dict[str, Any]:
    """Minimal config dict that passes validate_config (integrated proxy required)."""
    config: dict[str, Any] = {
        "GLOBAL": {"SERVER_ID": 1},
        "REPORTS": {"REPORT": False},
        "SYSTEMS": {
            "HOTSPOT": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 8,
            }
        },
        "PROXY": {
            "LISTEN_PORT": 62031,
            "TARGET_SYSTEM": "HOTSPOT",
            "TIMEOUT": 30,
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(config.get(key), dict):
            config[key] = {**config[key], **value}
        else:
            config[key] = value
    return config
