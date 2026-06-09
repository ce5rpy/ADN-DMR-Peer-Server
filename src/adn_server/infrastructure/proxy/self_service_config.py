"""SELF_SERVICE block from config (same keys as adn-monitor / adn-proxy)."""

from __future__ import annotations

from typing import Any


def self_service_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Resolved self-service settings; disabled when block missing or USE_SELFSERVICE false."""
    block = config.get("SELF_SERVICE") or {}
    if not isinstance(block, dict):
        block = {}
    enabled = bool(block.get("USE_SELFSERVICE", block.get("ENABLED", False)))
    return {
        "enabled": enabled,
        "db_server": str(block.get("DB_SERVER", "localhost")),
        "db_username": str(block.get("DB_USERNAME", "")),
        "db_password": str(block.get("DB_PASSWORD", "")),
        "db_name": str(block.get("DB_NAME", "")),
        "db_port": int(block.get("DB_PORT", 3306)),
        "pbkdf2_salt": str(block.get("PBKDF2_SALT", "ADN")),
        "pbkdf2_iterations": int(block.get("PBKDF2_ITERATIONS", 2000)),
    }
