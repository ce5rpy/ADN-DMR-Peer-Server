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

"""Report server: CONFIG_SND, BRIDGE_SND, BRDG_EVENT (legacy reportFactory, bridgeReportFactory)."""

from __future__ import annotations

import json
import logging
import pickle
from typing import Any

from twisted.internet.protocol import Factory
from twisted.protocols.basic import NetstringReceiver

logger = logging.getLogger(__name__)

REPORT_OPCODES = {
    "CONFIG_REQ": b"\x00",
    "CONFIG_SND": b"\x01",
    "BRIDGE_REQ": b"\x02",
    "BRIDGE_SND": b"\x03",
    "CONFIG_UPD": b"\x04",
    "BRIDGE_UPD": b"\x05",
    "LINK_EVENT": b"\x06",
    "BRDG_EVENT": b"\x07",
    "HELLO": b"\xff",
}

SERVER_NAME = "adn-server"
PROTOCOL_VERSION = 1
SERVER_FEATURES = ("INGRESS", "END_TX_FORWARD", "PUSH_ON_CONNECT")


def _server_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("adn-server")
        except PackageNotFoundError:
            return "0.0.0"
    except Exception:
        return "0.0.0"


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
        self._factory._send_config_to(self)
        self._factory._send_bridge_to(self)

    def connectionLost(self, reason: Any = None) -> None:
        if self in self._factory.clients:
            self._factory.clients.remove(self)
        logger.info("(REPORT) Client disconnected (%s client(s))", len(self._factory.clients))

    def stringReceived(self, data: bytes) -> None:
        if data[:1] == REPORT_OPCODES["CONFIG_REQ"]:
            self._factory._send_config_to(self)
        elif data[:1] == REPORT_OPCODES["BRIDGE_REQ"]:
            self._factory._send_bridge_to(self)
        else:
            pass  # unknown opcode


class ReportServerFactory(Factory):
    """Factory for report protocol; holds config and bridges and sends to clients."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
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

    def set_systems(self, systems: dict[str, Any]) -> None:
        self._systems = systems

    def set_bridges(self, bridges: dict[str, Any]) -> None:
        self._bridges = bridges

    def _send_hello_to(self, client: ReportProtocol) -> None:
        info = {
            "server": SERVER_NAME,
            "version": _server_version(),
            "protocol": PROTOCOL_VERSION,
            "features": list(SERVER_FEATURES),
        }
        payload = json.dumps(info, separators=(",", ":")).encode("utf-8")
        try:
            client.sendString(REPORT_OPCODES["HELLO"] + payload)
            logger.debug("(REPORT) Sent HELLO to client: %s", info)
        except Exception as e:
            logger.warning("(REPORT) Failed to send HELLO: %s", e)

    def _send_config_to(self, client: ReportProtocol) -> None:
        """Send CONFIG_SND to a single client (e.g. on connect or CONFIG_REQ)."""
        payload = pickle.dumps(self._systems, protocol=2)
        msg = REPORT_OPCODES["CONFIG_SND"] + payload
        client.sendString(msg)
        logger.debug("(REPORT) Sent CONFIG_SND to client (%d systems)", len(self._systems))

    def _send_bridge_to(self, client: ReportProtocol) -> None:
        """Send BRIDGE_SND to a single client (e.g. on connect or BRIDGE_REQ)."""
        payload = pickle.dumps(self._bridges, protocol=2)
        msg = REPORT_OPCODES["BRIDGE_SND"] + payload
        client.sendString(msg)
        logger.debug("(REPORT) Sent BRIDGE_SND to client (%d bridges)", len(self._bridges))

    def send_config(self) -> None:
        """Send CONFIG_SND (pickle SYSTEMS) to all clients."""
        n = len(self.clients)
        logger.debug("(REPORT) Sending CONFIG_SND to %s client(s)", n)
        for c in self.clients:
            self._send_config_to(c)

    def send_bridge(self) -> None:
        """Send BRIDGE_SND (pickle BRIDGES) to all clients."""
        n = len(self.clients)
        logger.debug("(REPORT) Sending BRIDGE_SND to %s client(s)", n)
        for c in self.clients:
            self._send_bridge_to(c)

    def send_bridge_event(self, event: str) -> None:
        """Send BRDG_EVENT."""
        msg = REPORT_OPCODES["BRDG_EVENT"] + event.encode("utf-8", errors="ignore")
        for c in self.clients:
            c.sendString(msg)
