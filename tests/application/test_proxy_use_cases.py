"""Proxy use cases and packet helpers (Phase 3)."""

from __future__ import annotations

import random

import pytest

from adn_server.application.proxy import ProxyUseCases, peer_id_from_packet
from adn_server.domain.proxy import ClientEndpoint, UpstreamPortRange
from adn_server.domain.result import is_fail, is_ok
from adn_server.domain.value_objects import bytes_4
from adn_server.infrastructure.proxy import InMemoryPendingRptoQueue, InMemoryProxySlotStore

_PORT_RANGE = UpstreamPortRange(port_start=56400, port_count=4)
_PEER_A = bytes_4(1234567)
_PEER_B = bytes_4(7654321)


def _service(*, black_list: tuple[int, ...] = (), seed: int = 1) -> ProxyUseCases:
    return ProxyUseCases(
        InMemoryProxySlotStore(_PORT_RANGE),
        _PORT_RANGE,
        InMemoryPendingRptoQueue(),
        black_list=black_list,
        rng=random.Random(seed),
    )


def test_attach_allocates_upstream_port_and_refreshes_client() -> None:
    svc = _service()
    first = svc.attach_client(_PEER_A, "10.0.0.1", 62031)
    assert is_ok(first)
    slot = first.value
    assert slot.upstream_port in _PORT_RANGE.ports()
    assert slot.client.host == "10.0.0.1"

    again = svc.attach_client(_PEER_A, "10.0.0.2", 62032)
    assert is_ok(again)
    assert again.value.upstream_port == slot.upstream_port
    assert again.value.client == ClientEndpoint(host="10.0.0.2", port=62032)


def test_attach_rejects_blacklisted_peer() -> None:
    svc = _service(black_list=(1234567,))
    result = svc.attach_client(_PEER_A, "10.0.0.1", 62031)
    assert is_fail(result)


def test_attach_fails_when_ports_exhausted() -> None:
    svc = _service()
    for n in range(4):
        peer = bytes_4(1000 + n)
        assert is_ok(svc.attach_client(peer, "10.0.0.1", 62031 + n))
    assert is_fail(svc.attach_client(bytes_4(9999), "10.0.0.9", 62099))


def test_detach_frees_upstream_port() -> None:
    svc = _service()
    slot = svc.attach_client(_PEER_A, "10.0.0.1", 62031).value
    removed = svc.detach_client(_PEER_A)
    assert removed == slot
    assert svc.resolve_upstream(_PEER_A) is None
    assert is_ok(svc.attach_client(_PEER_B, "10.0.0.5", 62035))


def test_resolve_client_by_upstream_port() -> None:
    svc = _service()
    slot = svc.attach_client(_PEER_A, "192.168.1.10", 12345).value
    client = svc.resolve_client(slot.upstream_port)
    assert client is not None
    assert client.host == "192.168.1.10"
    assert client.port == 12345


def test_schedule_and_dequeue_rpto() -> None:
    svc = _service()
    svc.attach_client(_PEER_A, "10.0.0.1", 62031)
    payload = b"TS1=123;TS2=456;"
    assert svc.schedule_rpto(_PEER_A, payload) is True
    assert svc.schedule_rpto(bytes_4(999), payload) is False
    pending = svc.next_pending_rpto()
    assert pending is not None
    assert pending.peer_id == _PEER_A
    assert pending.payload == payload
    assert pending.upstream_port == svc.resolve_upstream(_PEER_A)


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
