# ADN DMR Peer Server - TCP report server
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

"""Report server: CONFIG_SND, BRIDGE_SND, BRDG_EVENT (legacy reportFactory, bridgeReportFactory)."""

from __future__ import annotations

import logging
import pickle
from typing import Any

from twisted.internet.protocol import Factory
from twisted.protocols.basic import NetstringReceiver

logger = logging.getLogger(__name__)

# Same opcodes as legacy reporting_const
REPORT_OPCODES = {
    "CONFIG_REQ": b"\x00",
    "CONFIG_SND": b"\x01",
    "BRIDGE_REQ": b"\x02",
    "BRIDGE_SND": b"\x03",
    "CONFIG_UPD": b"\x04",
    "BRIDGE_UPD": b"\x05",
    "LINK_EVENT": b"\x06",
    "BRDG_EVENT": b"\x07",
}


class ReportProtocol(NetstringReceiver):
    """Single report client connection."""

    def __init__(self, factory: "ReportServerFactory") -> None:
        self._factory = factory

    def connectionMade(self) -> None:
        self._factory.clients.append(self)
        peer = self.transport.getPeer() if self.transport else None
        addr = f"{peer.host}:{peer.port}" if peer else "?"
        logger.info("(REPORT) Client connected from %s (%s client(s))", addr, len(self._factory.clients))
        # Send CONFIG_SND and BRIDGE_SND immediately so monitor gets systems/bridges without waiting for loop
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
