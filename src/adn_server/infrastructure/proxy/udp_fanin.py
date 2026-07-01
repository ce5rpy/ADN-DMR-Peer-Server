# ADN DMR Peer Server - infrastructure proxy udp fanin
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

"""UDP fan-in: hotspot LISTEN_PORT with in-process inject (Phase 3)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

from twisted.internet.protocol import DatagramProtocol

from adn_server.application.ports import ProxyMasterSink
from adn_server.application.proxy import ProxyUseCases, peer_id_from_packet
from adn_server.domain.result import is_fail
from adn_server.infrastructure.hbp_constants import RPTC, RPTO

if TYPE_CHECKING:
    from .self_service_bridge import ProxySelfServiceBridge

_logger = logging.getLogger(__name__)

_CONTROL_COMMANDS = frozenset({RPTC, RPTO})


class _DatagramWriter(Protocol):
    def write(self, data: bytes, addr: tuple[str, int]) -> None:
        ...


class ProxyFanInProtocol(DatagramProtocol):
    """UDP listener for hotspots; attaches sessions and injects into the target MASTER."""

    def __init__(
        self,
        proxy: ProxyUseCases,
        master_sink: ProxyMasterSink,
        *,
        debug: bool = False,
        logger: logging.Logger | None = None,
        on_attached: Callable[[bytes, str, int, bool], None] | None = None,
        self_service: ProxySelfServiceBridge | None = None,
    ) -> None:
        self._proxy = proxy
        self._master_sink = master_sink
        self.debug = debug
        self._log = logger or _logger
        self._on_attached = on_attached
        self._self_service = self_service

    def datagramReceived(self, data: bytes, addr: tuple[str, int]) -> None:
        host, port = addr
        if self._proxy.is_ip_blocked(host):
            if self.debug:
                self._log.debug("(PROXY) dropped packet from blacklisted IP %s:%s", host, port)
            return
        command = data[:4] if len(data) >= 4 else b""
        if self.debug:
            self._log.debug(
                "(PROXY) RX from %s:%s len=%d cmd=%r",
                host,
                port,
                len(data),
                command,
            )
        peer_id = peer_id_from_packet(data, from_master=False)
        if peer_id is None:
            if self.debug:
                self._log.debug("(PROXY) ignored packet with no peer_id from %s:%s", host, port)
            return
        new_session = self._proxy.resolve_client(peer_id) is None
        result = self._proxy.attach_client(peer_id, host, port)
        if is_fail(result):
            if self.debug or command in _CONTROL_COMMANDS:
                self._log.warning(
                    "(PROXY) attach rejected peer=%s from %s:%s: %s (cmd=%r)",
                    peer_id.hex(),
                    host,
                    port,
                    result.error,
                    command,
                )
            return
        if self._on_attached is not None:
            self._on_attached(peer_id, host, port, new_session)
        if self._self_service is not None and self._self_service.before_inject(
            data, addr, peer_id
        ):
            return
        self._master_sink.inject(data, addr)


def listen_proxy_fanin(
    reactor: Any,
    listen_ip: str,
    listen_port: int,
    proxy: ProxyUseCases,
    master_sink: ProxyMasterSink,
    *,
    debug: bool = False,
    logger: logging.Logger | None = None,
    protocol: ProxyFanInProtocol | None = None,
) -> tuple[ProxyFanInProtocol, Any]:
    """Bind LISTEN_PORT and return ``(protocol, udp_port)``."""
    fanin = protocol or ProxyFanInProtocol(proxy, master_sink, debug=debug, logger=logger)
    udp_port = reactor.listenUDP(listen_port, fanin, interface=listen_ip or "0.0.0.0")
    return fanin, udp_port


__all__ = ["ProxyFanInProtocol", "listen_proxy_fanin"]
