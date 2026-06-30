# ADN DMR Peer Server - tests infrastructure mesh obp v1
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

"""Unit tests for OpenBridge v1 HMAC wire codec."""

from __future__ import annotations

from adn_server.domain import bytes_4
from adn_server.infrastructure.hbp_constants import BCKA, BCSQ, BCST, BCVE, DMRD
from adn_server.infrastructure.mesh.obp_v1 import obp_hmac_sha1
from adn_server.infrastructure.mesh.obp_v1 import (
    DMRD_V1_WIRE_LEN,
    build_bcka,
    build_bcsq,
    build_bcve,
    build_dmrd_v1,
    verify_bcka,
    verify_bcsq,
    verify_bcst,
    verify_bcve,
    verify_dmrd_v1,
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


def test_dmrd_v1_roundtrip() -> None:
    inner = _sample_dmr_voice()
    wire = build_dmrd_v1(inner, bytes_4(9990), _PASS)
    assert len(wire) == DMRD_V1_WIRE_LEN
    verified = verify_dmrd_v1(wire, _PASS)
    assert verified is not None
    assert verified.payload[:4] == DMRD


def test_bcka_roundtrip() -> None:
    wire = build_bcka(_PASS)
    assert wire[:4] == BCKA
    assert verify_bcka(wire, _PASS)
    assert not verify_bcka(wire[:20], _PASS)


def test_bcst_roundtrip() -> None:
    wire = BCST + obp_hmac_sha1(_PASS, BCST)
    assert wire[:4] == BCST
    assert verify_bcst(wire, _PASS)


def test_bcve_roundtrip() -> None:
    wire = build_bcve(5, _PASS)
    assert wire[:4] == BCVE
    ok, ver = verify_bcve(wire, _PASS)
    assert ok and ver == 5


def test_bcsq_roundtrip() -> None:
    tgid = bytes_4(52090)[1:4]
    stream = bytes_4(0x11223344)
    wire = build_bcsq(tgid, stream, _PASS)
    assert wire[:4] == BCSQ
    verified = verify_bcsq(wire, _PASS)
    assert verified is not None
    assert verified.tgid == tgid
    assert verified.stream_id == stream
