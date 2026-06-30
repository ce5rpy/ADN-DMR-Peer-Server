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
from collections.abc import Callable
from typing import Any

from twisted.internet.protocol import Factory
from twisted.protocols.basic import NetstringReceiver

from adn_server.application.ports import ReportMqttPublisher, ReportWireEncoder
from adn_server.application.report.monitor_topology import (
    expand_inject_proxy_systems,
    remap_inject_proxy_voice_events,
)
from adn_server.application.routing.downlink import DownlinkContext

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
        self._factory._send_state_to(self, force=True)

    def connectionLost(self, reason: Any = None) -> None:
        if self in self._factory.clients:
            self._factory.clients.remove(self)
        logger.info("(REPORT) Client disconnected (%s client(s))", len(self._factory.clients))

    def stringReceived(self, data: bytes) -> None:
        if data[:1] in (
            REPORT_OPCODES["STATE_REQ"],
            REPORT_OPCODES["CONFIG_REQ"],
            REPORT_OPCODES["BRIDGE_REQ"],
        ):
            self._factory._send_state_to(self, force=True)


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
        self._peer_slot_map: Callable[[], dict[bytes, int]] | None = None
        self._downlink_ctx_for_system: Callable[[str], DownlinkContext | None] | None = None

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

    def set_routing_table(self, bridges: dict[str, Any]) -> None:
        self._bridges = bridges

    def set_peer_slot_map(self, provider: Callable[[], dict[bytes, int]] | None) -> None:
        """Provide proxy upstream slot indices for monitor topology expansion."""
        self._peer_slot_map = provider

    def set_downlink_ctx_for_system(
        self,
        provider: Callable[[str], DownlinkContext | None] | None,
    ) -> None:
        """Provide per-MASTER downlink state for monitor voice-event gating."""
        self._downlink_ctx_for_system = provider

    def _systems_for_report(self) -> dict[str, Any]:
        systems = self._systems
        peer_slots = self._peer_slot_map() if self._peer_slot_map is not None else None
        return expand_inject_proxy_systems(self._config, systems, peer_slots)

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
            self._send_frames(client, self._wire.hello_frames(self._systems_for_report()))
        except Exception as e:
            logger.warning("(REPORT) Failed to send HELLO: %s", e)

    def _send_state_to(self, client: ReportProtocol, *, force: bool) -> None:
        self._send_frames(
            client,
            self._wire.state_frames(self._systems_for_report(), force=force),
        )

    def send_config(self, *, incremental: bool = False) -> None:
        systems = self._systems_for_report()
        frames = self._wire.state_frames(systems, force=not incremental)
        self._broadcast_frames(frames)
        if self._mqtt is not None:
            self._mqtt.publish_dashboard(systems)

    def send_routing_table(self, *, incremental: bool = False) -> None:
        frames = self._wire.bridge_frames(self._bridges, full_snapshot=not incremental)
        self._broadcast_frames(frames)
        if self._mqtt is not None:
            self._mqtt.publish_dashboard(self._systems_for_report())

    def send_routing_event(self, event: str) -> None:
        peer_slots = self._peer_slot_map() if self._peer_slot_map is not None else None
        downlink_ctx = None
        if self._downlink_ctx_for_system is not None:
            target = self._config.get("PROXY", {}).get("TARGET_SYSTEM")
            if isinstance(target, str) and target:
                downlink_ctx = self._downlink_ctx_for_system(target)
        events = remap_inject_proxy_voice_events(
            event,
            self._config,
            self._systems,
            peer_slots,
            self._bridges,
            downlink_ctx,
        )
        for mapped in events:
            frames = self._wire.bridge_event_frames(mapped)
            self._broadcast_frames(frames)
            if self._mqtt is not None:
                self._mqtt.publish_frames(frames)

