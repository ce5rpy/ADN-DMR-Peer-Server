# ADN DMR Peer Server - tests application proxy use cases
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

"""Proxy use cases and packet helpers (Phase 3)."""

from __future__ import annotations

import time

import pytest

from adn_server.application.proxy import ProxyUseCases, peer_id_from_packet
from adn_server.domain.proxy import ClientEndpoint
from adn_server.domain.result import is_fail
from adn_server.domain.result import Success
from adn_server.domain.value_objects import bytes_4
from adn_server.infrastructure.proxy import InMemoryPendingRptoQueue, InMemoryProxySlotStore

_PEER_A = bytes_4(1234567)
_PEER_B = bytes_4(7654321)
_MAX_PEERS = 4


def _service(*, max_peers: int = _MAX_PEERS, black_list: tuple[int, ...] = ()) -> ProxyUseCases:
    return ProxyUseCases(
        InMemoryProxySlotStore(),
        InMemoryPendingRptoQueue(),
        max_peers=max_peers,
        black_list=black_list,
    )


def test_attach_creates_session_and_refreshes_client() -> None:
    svc = _service()
    first = svc.attach_client(_PEER_A, "10.0.0.1", 62031)
    assert isinstance(first, Success)
    slot = first.value
    assert slot.client == ClientEndpoint(host="10.0.0.1", port=62031)

    again = svc.attach_client(_PEER_A, "10.0.0.2", 62032)
    assert isinstance(again, Success)
    assert again.value.client == ClientEndpoint(host="10.0.0.2", port=62032)
    assert len(svc.list_slots()) == 1


def test_attach_rejects_blacklisted_peer() -> None:
    svc = _service(black_list=(1234567,))
    result = svc.attach_client(_PEER_A, "10.0.0.1", 62031)
    assert is_fail(result)


def test_attach_fails_when_max_peers_exceeded() -> None:
    svc = _service(max_peers=4)
    for n in range(4):
        peer = bytes_4(1000 + n)
        assert isinstance(svc.attach_client(peer, "10.0.0.1", 62031 + n), Success)
    assert is_fail(svc.attach_client(bytes_4(9999), "10.0.0.9", 62099))


def test_detach_removes_session() -> None:
    svc = _service(max_peers=4)
    slot = svc.attach_client(_PEER_A, "10.0.0.1", 62031).value
    removed = svc.detach_client(_PEER_A)
    assert removed == slot
    assert svc.resolve_client(_PEER_A) is None
    assert isinstance(svc.attach_client(_PEER_B, "10.0.0.5", 62035), Success)


def test_resolve_client_by_peer_id() -> None:
    svc = _service()
    svc.attach_client(_PEER_A, "192.168.1.10", 12345)
    client = svc.resolve_client(_PEER_A)
    assert client is not None
    assert client.host == "192.168.1.10"
    assert client.port == 12345


def test_expire_session_returns_teardown_plan() -> None:
    svc = _service()
    svc.attach_client(_PEER_A, "10.0.0.1", 62031)
    teardown = svc.expire_session(_PEER_A)
    assert teardown is not None
    assert teardown.peer_id == _PEER_A
    assert teardown.client.host == "10.0.0.1"
    assert svc.resolve_client(_PEER_A) is None


def test_ip_blacklist_blocks_attach() -> None:
    from adn_server.infrastructure.proxy import InMemoryProxyIpBlacklist

    bl = InMemoryProxyIpBlacklist()
    bl.block_until("10.0.0.9", time.time() + 60)
    svc = ProxyUseCases(
        InMemoryProxySlotStore(),
        InMemoryPendingRptoQueue(),
        ip_blacklist=bl,
    )
    assert is_fail(svc.attach_client(_PEER_A, "10.0.0.9", 62031))


def test_attach_client_assigns_report_slot() -> None:
    svc = _service(max_peers=4)
    first = svc.attach_client(_PEER_A, "10.0.0.1", 62031)
    second = svc.attach_client(_PEER_B, "10.0.0.2", 62032)
    assert isinstance(first, Success)
    assert isinstance(second, Success)
    assert first.value.report_slot == 0
    assert second.value.report_slot == 1


@pytest.mark.parametrize(
    ("data", "from_master", "expected"),
    [
        (b"RPTL" + _PEER_A + b"\x00", False, _PEER_A),
        (b"DMRD" + b"\x00" * 7 + _PEER_A + b"\x00", False, _PEER_A),
        (b"DMRD" + b"\x00" * 7 + _PEER_B, True, _PEER_B),
        (b"RPTA" + b"\x00" * 2 + _PEER_A, True, _PEER_A),
        (b"RPTL\x00", False, None),
    ],
)
def test_peer_id_from_packet(data: bytes, from_master: bool, expected: bytes | None) -> None:
    assert peer_id_from_packet(data, from_master=from_master) == expected
