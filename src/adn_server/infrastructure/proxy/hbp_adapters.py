# ADN DMR Peer Server - infrastructure proxy hbp adapters
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

"""HBP adapters for proxy application ports."""

from __future__ import annotations

from typing import Any, Protocol

from adn_server.application.ports import MasterPeerRegistry, ProxyClientSender, ProxyMasterSink
from adn_server.domain.proxy import ClientEndpoint


class _MasterHbpReceiver(Protocol):
    def _master_datagram_received(self, data: bytes, sockaddr: tuple[str, int]) -> None:
        ...


class InProcessHbpSink(ProxyMasterSink):
    """Deliver client datagrams to the target MASTER without a UDP hop."""

    def __init__(self, hbp: _MasterHbpReceiver) -> None:
        self._hbp = hbp

    def inject(self, data: bytes, client_addr: tuple[str, int]) -> None:
        self._hbp._master_datagram_received(data, client_addr)


class FanInClientSender(ProxyClientSender):
    """Send to hotspots through the fan-in UDP transport."""

    def __init__(self, transport: Any) -> None:
        self._transport = transport

    def send_to_client(self, data: bytes, client: ClientEndpoint) -> None:
        if self._transport is None:
            return
        self._transport.write(data, (client.host, client.port))


class HbpMasterPeerRegistry(MasterPeerRegistry):
    """Remove timed-out peers from MASTER ``_peers``."""

    def __init__(self, hbp: Any) -> None:
        self._hbp = hbp

    def remove_peer(self, peer_id: bytes) -> None:
        on_disconnect = getattr(self._hbp, "_on_peer_disconnected", None)
        if callable(on_disconnect):
            on_disconnect(peer_id)
        peers = getattr(self._hbp, "_peers", None)
        if isinstance(peers, dict):
            peers.pop(peer_id, None)
