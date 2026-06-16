# ADN DMR Peer Server - tests infrastructure logging reload
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
