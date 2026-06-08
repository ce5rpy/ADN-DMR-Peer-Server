"""Unit tests for DMRE v4/v5 BLAKE2b wire codec."""

from __future__ import annotations

from adn_server.domain import bytes_4
from adn_server.domain.hbp_protocol import VER
from adn_server.infrastructure.hbp_constants import DMRD, DMRE
from adn_server.infrastructure.mesh.dmre_v5 import (
    build_dmre,
    parse_dmre_trailer,
    verify_dmre_mac,
)

_PASS = b"test-passphrase\x00\x00\x00\x00\x00\x00"


def _sample_dmr_voice() -> bytes:
    return b"".join(
        [
            DMRD,
            bytes([1]),
            bytes_4(1001)[1:4],
            bytes_4(52090)[1:4],
            bytes_4(1),
            bytes([0x10]),
            bytes_4(0xAABBCCDD),
            b"\x00" * 33,
        ]
    )


def test_dmre_v5_extended_layout() -> None:
    inner = _sample_dmr_voice()
    wire = build_dmre(
        inner,
        server_id=bytes_4(9990),
        ber=b"\x00",
        rssi=b"\x00",
        embedded_ver=VER,
        timestamp_ns=1_700_000_000_000_000_000,
        source_server=bytes_4(9990),
        source_rptr=bytes_4(100),
        hops=b"\x01",
        passphrase=_PASS,
        extended_layout=True,
    )
    assert wire is not None
    assert len(wire) == 89
    assert wire[:4] == DMRE
    trailer = parse_dmre_trailer(wire)
    assert trailer is not None
    assert trailer.hash_len == 73
    assert verify_dmre_mac(wire, _PASS, trailer.hash_len)


def test_dmre_v4_compact_layout() -> None:
    inner = _sample_dmr_voice()
    wire = build_dmre(
        inner,
        server_id=bytes_4(9990),
        ber=b"\x00",
        rssi=b"\x00",
        embedded_ver=4,
        timestamp_ns=1_700_000_000_000_000_000,
        source_server=bytes_4(9990),
        source_rptr=b"\x00\x00\x00\x00",
        hops=b"\x01",
        passphrase=_PASS,
        extended_layout=False,
    )
    assert wire is not None
    assert len(wire) == 85
    trailer = parse_dmre_trailer(wire)
    assert trailer is not None
    assert trailer.hash_len == 69
    assert verify_dmre_mac(wire, _PASS, trailer.hash_len)
