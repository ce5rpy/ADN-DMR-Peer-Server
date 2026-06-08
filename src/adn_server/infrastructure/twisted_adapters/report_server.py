# ADN DMR Peer Server - TCP report server
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

"""TCP report transport (Twisted). Encoding delegated to ``report/`` wire adapters."""

from __future__ import annotations

import logging
from typing import Any

from twisted.internet.protocol import Factory
from twisted.protocols.basic import NetstringReceiver

from adn_server.application.ports import ReportMqttPublisher, ReportWireEncoder

from .report import REPORT_OPCODES, create_report_wire

logger = logging.getLogger(__name__)

__all__ = ["REPORT_OPCODES", "ReportServerFactory"]


class ReportProtocol(NetstringReceiver):
    """Single report client connection."""

    def __init__(self, factory: "ReportServerFactory") -> None:
        self._factory = factory

    def connectionMade(self) -> None:
        self._factory.clients.append(self)
        peer = self.transport.getPeer() if self.transport else None
        addr = f"{peer.host}:{peer.port}" if peer else "?"
        logger.info("(REPORT) Client connected from %s (%s client(s))", addr, len(self._factory.clients))
        self._factory._send_hello_to(self)
        self._factory._send_config_to(self, full_snapshot=True)
        self._factory._send_bridge_to(self, full_snapshot=True)

    def connectionLost(self, reason: Any = None) -> None:
        if self in self._factory.clients:
            self._factory.clients.remove(self)
        logger.info("(REPORT) Client disconnected (%s client(s))", len(self._factory.clients))

    def stringReceived(self, data: bytes) -> None:
        if data[:1] == REPORT_OPCODES["CONFIG_REQ"]:
            self._factory._send_config_to(self, full_snapshot=True)
        elif data[:1] == REPORT_OPCODES["BRIDGE_REQ"]:
            self._factory._send_bridge_to(self, full_snapshot=True)


class ReportServerFactory(Factory):
    """Twisted factory: ACL, client list, broadcast via injected ``ReportWireEncoder``."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        mqtt: ReportMqttPublisher | None = None,
    ) -> None:
        self._config = config
        self._wire: ReportWireEncoder = create_report_wire(config)
        self._mqtt = mqtt
        self.clients: list[ReportProtocol] = []
        self._systems: dict[str, Any] = {}
        self._bridges: dict[str, Any] = {}

    def buildProtocol(self, addr: Any) -> ReportProtocol | None:
        allowed = self._config.get("REPORTS", {}).get("REPORT_CLIENTS", ["127.0.0.1"])
        if isinstance(allowed, str):
            allowed = [x.strip() for x in allowed.split(",")]
        if "*" in allowed or (hasattr(addr, "host") and addr.host in allowed):
            return ReportProtocol(self)
        return None

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = config

    def set_mqtt(self, mqtt: ReportMqttPublisher | None) -> None:
        self._mqtt = mqtt

    def set_systems(self, systems: dict[str, Any]) -> None:
        self._systems = systems

    def set_bridges(self, bridges: dict[str, Any]) -> None:
        self._bridges = bridges

    def _send_frames(self, client: ReportProtocol, frames: tuple[bytes, ...]) -> None:
        for frame in frames:
            client.sendString(frame)

    def _broadcast_frames(self, frames: tuple[bytes, ...]) -> None:
        if not frames:
            return
        for client in self.clients:
            self._send_frames(client, frames)

    def start_mqtt(self) -> None:
        if self._mqtt is not None:
            self._mqtt.start(self._wire, lambda: self._systems, lambda: self._bridges)

    def _send_hello_to(self, client: ReportProtocol) -> None:
        try:
            self._send_frames(client, self._wire.hello_frames(self._systems))
        except Exception as e:
            logger.warning("(REPORT) Failed to send HELLO: %s", e)

    def _send_config_to(self, client: ReportProtocol, *, full_snapshot: bool) -> None:
        self._send_frames(client, self._wire.config_frames(self._systems, full_snapshot=full_snapshot))

    def _send_bridge_to(self, client: ReportProtocol, *, full_snapshot: bool) -> None:
        self._send_frames(client, self._wire.bridge_frames(self._bridges, full_snapshot=full_snapshot))

    def send_config(self, *, incremental: bool = False) -> None:
        frames = self._wire.config_frames(self._systems, full_snapshot=not incremental)
        self._broadcast_frames(frames)
        if self._mqtt is not None:
            self._mqtt.publish_dashboard(self._systems)

    def send_bridge(self, *, incremental: bool = False) -> None:
        frames = self._wire.bridge_frames(self._bridges, full_snapshot=not incremental)
        self._broadcast_frames(frames)

    def send_bridge_event(self, event: str) -> None:
        frames = self._wire.bridge_event_frames(event)
        self._broadcast_frames(frames)
        if self._mqtt is not None:
            self._mqtt.publish_frames(frames)
