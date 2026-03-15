# ADN DMR Peer Server - reporting use cases
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

"""Reporting: send config/bridge to TCP clients, KA reporting. Orchestrates ReportSender."""

from __future__ import annotations

import logging
import time
from typing import Any

from .ports import ReportSender

logger = logging.getLogger(__name__)


class ReportingUseCases:
    """Use cases for TCP report server and keepalive reporting."""

    def __init__(self, report_sender: ReportSender, config: dict[str, Any]) -> None:
        self._sender = report_sender
        self._config = config

    def send_config(self, systems: dict[str, Any]) -> None:
        """Send CONFIG_SND to all report clients."""
        self._sender.send_config(systems)

    def send_bridge(self, bridges: dict[str, Any]) -> None:
        """Send BRIDGE_SND to all report clients."""
        self._sender.send_bridge(bridges)

    def send_bridge_event(self, event: str) -> None:
        """Send BRDG_EVENT to all report clients."""
        self._sender.send_bridge_event(event)

    def ka_reporting_loop(self) -> None:
        """Legacy kaReporting (60s): check OBP keepalive status and log warnings for stale connections."""
        logger.debug("(ROUTER) KeepAlive reporting loop started")
        systems_cfg = self._config.get("SYSTEMS", {})
        now = time.time()
        for system_name, sys_cfg in systems_cfg.items():
            if sys_cfg.get("MODE") == "OPENBRIDGE" and sys_cfg.get("ENHANCED_OBP"):
                if "_bcka" not in sys_cfg:
                    logger.warning("(ROUTER) not sending to system %s as KeepAlive never seen", system_name)
                elif sys_cfg["_bcka"] < now - 60:
                    logger.warning(
                        "(ROUTER) not sending to system %s as last KeepAlive was %s seconds ago",
                        system_name, int(now - sys_cfg["_bcka"]),
                    )
