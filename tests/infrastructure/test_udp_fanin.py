# ADN DMR Peer Server - tests infrastructure udp fanin
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

"""UDP fan-in protocol tests (no live reactor)."""

from __future__ import annotations

from unittest.mock import MagicMock

from adn_server.application.proxy import ProxyUseCases
from adn_server.domain.value_objects import bytes_4
from adn_server.infrastructure.config_normalizer import ensure_system_runtime_config
from adn_server.infrastructure.hbp_constants import RPTACK, RPTL
from adn_server.infrastructure.proxy import (
    InMemoryPendingRptoQueue,
    InMemoryProxySlotStore,
    InProcessHbpSink,
    ProxyFanInProtocol,
    ProxyReplyTransport,
)
from adn_server.infrastructure.twisted_adapters.udp_hbp import HBPProtocol

_PEER = bytes_4(1234567)
_CLIENT_ADDR = ("192.168.1.50", 62031)


class _RecordingTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def write(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))


class _AclRouter:
    def acl_check(self, peer_id: bytes, acl: object) -> bool:
        return True


def _hotspot_master_config() -> dict:
    config = {
        "GLOBAL": {"PING_TIME": 10, "MAX_MISSED": 3, "USE_ACL": False},
        "SYSTEMS": {
            "HOTSPOT": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 8,
                "OPTIONS": "TS2=9990;",
            }
        },
    }
    ensure_system_runtime_config(config)
    return config


def _fanin_stack(*, max_peers: int = 8) -> tuple[ProxyFanInProtocol, ProxyUseCases, InProcessHbpSink, _RecordingTransport, MagicMock]:
    transport = _RecordingTransport()
    config = _hotspot_master_config()
    hbp = HBPProtocol("HOTSPOT", config)
    hbp._router = _AclRouter()  # type: ignore[assignment]
    hbp.transport = ProxyReplyTransport(transport)
    sink = InProcessHbpSink(hbp)
    inject_spy = MagicMock(wraps=sink.inject)
    sink.inject = inject_spy  # type: ignore[method-assign]
    proxy = ProxyUseCases(
        InMemoryProxySlotStore(),
        InMemoryPendingRptoQueue(),
        max_peers=max_peers,
    )
    protocol = ProxyFanInProtocol(proxy, sink)
    protocol.transport = transport  # type: ignore[assignment]
    return protocol, proxy, sink, transport, inject_spy


def test_client_packet_attaches_session_and_injects() -> None:
    protocol, proxy, _, _, inject_spy = _fanin_stack()
    packet = RPTL + _PEER
    protocol.datagramReceived(packet, _CLIENT_ADDR)
    inject_spy.assert_called_once_with(packet, _CLIENT_ADDR)
    slot = proxy.resolve_client(_PEER)
    assert slot is not None
    assert slot.host == _CLIENT_ADDR[0]
    assert slot.port == _CLIENT_ADDR[1]


def test_existing_client_refreshes_endpoint_before_inject() -> None:
    protocol, proxy, _, _, inject_spy = _fanin_stack()
    packet = RPTL + _PEER
    protocol.datagramReceived(packet, _CLIENT_ADDR)
    inject_spy.reset_mock()
    new_addr = ("192.168.1.51", 62040)
    protocol.datagramReceived(packet, new_addr)
    inject_spy.assert_called_once_with(packet, new_addr)
    client = proxy.resolve_client(_PEER)
    assert client is not None
    assert client.host == new_addr[0]
    assert client.port == new_addr[1]


def test_master_rptl_reply_sent_via_proxy_listen_socket() -> None:
    protocol, _, _, transport, _ = _fanin_stack()
    protocol.datagramReceived(RPTL + _PEER, _CLIENT_ADDR)
    assert len(transport.sent) == 1
    data, addr = transport.sent[0]
    assert data.startswith(RPTACK)
    assert addr == _CLIENT_ADDR


def test_attach_rejection_skips_inject() -> None:
    protocol, _, _, _, inject_spy = _fanin_stack(max_peers=0)
    protocol.datagramReceived(RPTL + _PEER, _CLIENT_ADDR)
    inject_spy.assert_not_called()
