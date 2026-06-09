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
        peers = getattr(self._hbp, "_peers", None)
        if isinstance(peers, dict):
            peers.pop(peer_id, None)
