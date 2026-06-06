"""Tests for LOGGER hot-reload level application."""

from __future__ import annotations

import logging

from adn_server.infrastructure.logging_config import reapply_log_level


def test_reapply_log_level_updates_root_and_named_logger() -> None:
    logging.basicConfig(level=logging.WARNING, force=True)
    app = logging.getLogger("adn-server")
    app.setLevel(logging.WARNING)

    name = reapply_log_level({"LOG_LEVEL": "DEBUG", "LOG_NAME": "adn-server"})

    assert name == "DEBUG"
    assert logging.getLogger().level == logging.DEBUG
    assert app.level == logging.DEBUG


def test_reapply_log_level_disabled_logger_uses_critical() -> None:
    name = reapply_log_level({"ENABLED": False, "LOG_LEVEL": "DEBUG", "LOG_NAME": "adn-server"})
    assert name == "CRITICAL"
    assert logging.getLogger("adn-server").level == logging.CRITICAL
