# ADN DMR Peer Server - infrastructure mesh obp v1
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

"""OpenBridge protocol v1: DMRD + HMAC-SHA1 control packets (no Twisted)."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from hmac import compare_digest
from hmac import new as hmac_new

from ..hbp_constants import BCKA, BCSQ, BCST, BCVE, DMRD

OBP_HMAC_LEN = 20
DMRD_V1_PAYLOAD_LEN = 53
DMRD_V1_WIRE_LEN = DMRD_V1_PAYLOAD_LEN + OBP_HMAC_LEN


def obp_hmac_sha1(passphrase: bytes, data: bytes) -> bytes:
    return hmac_new(passphrase, data, sha1).digest()


@dataclass(frozen=True)
class VerifiedDmrdV1:
    payload: bytes  # 53 bytes including DMRD header


@dataclass(frozen=True)
class VerifiedBcsq:
    tgid: bytes
    stream_id: bytes


def build_dmrd_v1(dmr_packet: bytes, server_id: bytes, passphrase: bytes) -> bytes:
    """Wire DMRD v1 (53 + HMAC) from a DMR/DMRD inner voice packet."""
    packet = b"".join([DMRD, dmr_packet[4:11], server_id, dmr_packet[15:]])
    return packet + obp_hmac_sha1(passphrase, packet)


def verify_dmrd_v1(packet: bytes, passphrase: bytes) -> VerifiedDmrdV1 | None:
    if packet[:4] != DMRD or len(packet) < DMRD_V1_WIRE_LEN:
        return None
    payload = packet[:DMRD_V1_PAYLOAD_LEN]
    mac = packet[DMRD_V1_PAYLOAD_LEN:DMRD_V1_WIRE_LEN]
    if not compare_digest(mac, obp_hmac_sha1(passphrase, payload)):
        return None
    return VerifiedDmrdV1(payload=payload)


def build_bcka(passphrase: bytes) -> bytes:
    return BCKA + obp_hmac_sha1(passphrase, BCKA)


def verify_bcka(packet: bytes, passphrase: bytes) -> bool:
    if packet[:4] != BCKA or len(packet) < 4 + OBP_HMAC_LEN:
        return False
    return compare_digest(packet[4:24], obp_hmac_sha1(passphrase, packet[:4]))


def build_bcve(ver: int, passphrase: bytes) -> bytes:
    packet = BCVE + ver.to_bytes(1, "big")
    return packet + obp_hmac_sha1(passphrase, packet[4:5])


def verify_bcve(packet: bytes, passphrase: bytes) -> tuple[bool, int | None]:
    if packet[:4] != BCVE or len(packet) < 25:
        return False, None
    ver = int.from_bytes(packet[4:5], "big")
    ok = compare_digest(packet[5:25], obp_hmac_sha1(passphrase, packet[4:5]))
    return ok, ver if ok else None


def build_bcsq(tgid: bytes, stream_id: bytes, passphrase: bytes) -> bytes:
    packet = BCSQ + tgid + stream_id
    return packet + obp_hmac_sha1(passphrase, packet)


def verify_bcsq(packet: bytes, passphrase: bytes) -> VerifiedBcsq | None:
    if packet[:4] != BCSQ or len(packet) < 31:
        return None
    mac = packet[11:31]
    if not compare_digest(mac, obp_hmac_sha1(passphrase, packet[:11])):
        return None
    return VerifiedBcsq(tgid=packet[4:7], stream_id=packet[7:11])


def verify_bcst(packet: bytes, passphrase: bytes) -> bool:
    if packet[:4] != BCST or len(packet) < 4 + OBP_HMAC_LEN:
        return False
    return compare_digest(packet[4:24], obp_hmac_sha1(passphrase, packet[:4]))
