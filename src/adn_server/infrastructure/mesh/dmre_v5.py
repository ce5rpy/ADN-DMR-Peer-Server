"""FreeBridge DMRE v4/v5: BLAKE2b wire build and parse (no Twisted)."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from hmac import compare_digest

from ..hbp_constants import DMRE

DMRE_DMR_PAYLOAD_LEN = 53
DMRE_MAC_LEN = 16


@dataclass(frozen=True)
class DmreTrailer:
    """Fields after the 53-byte DMR payload in a DMRE datagram."""

    embedded_version: int
    ber: bytes
    rssi: bytes
    timestamp: bytes
    source_server: bytes
    source_rptr: bytes
    hops: bytes
    hash_len: int  # authenticated prefix length (MAC starts here)


def dmre_blake2b_mac(packet: bytes, passphrase: bytes, hash_len: int) -> bytes:
    h = blake2b(key=passphrase, digest_size=DMRE_MAC_LEN)
    h.update(packet[:hash_len])
    return h.digest()


def verify_dmre_mac(packet: bytes, passphrase: bytes, hash_len: int) -> bool:
    if len(packet) < hash_len + DMRE_MAC_LEN:
        return False
    expected = packet[hash_len : hash_len + DMRE_MAC_LEN]
    return compare_digest(expected, dmre_blake2b_mac(packet, passphrase, hash_len))


def parse_dmre_trailer(packet: bytes) -> DmreTrailer | None:
    """Parse DMRE trailer; returns None if packet is too short or not DMRE."""
    if packet[:4] != DMRE or len(packet) < 69:
        return None
    embedded_version = packet[55]
    ber = packet[53:54]
    rssi = packet[54:55]
    timestamp = packet[56:64]
    if embedded_version > 4:
        if len(packet) < 89:
            return None
        source_server = packet[64:68]
        source_rptr = packet[68:72]
        hops = packet[72:73]
        hash_len = 73
    else:
        if len(packet) < 85:
            return None
        source_server = packet[64:68]
        source_rptr = b"\x00\x00\x00\x00"
        hops = packet[68:69]
        hash_len = 69
    return DmreTrailer(
        embedded_version=embedded_version,
        ber=ber,
        rssi=rssi,
        timestamp=timestamp,
        source_server=source_server,
        source_rptr=source_rptr,
        hops=hops,
        hash_len=hash_len,
    )


def build_dmre(
    dmr_packet: bytes,
    *,
    server_id: bytes,
    ber: bytes,
    rssi: bytes,
    embedded_ver: int,
    timestamp_ns: int,
    source_server: bytes,
    source_rptr: bytes,
    hops: bytes,
    passphrase: bytes,
    extended_layout: bool,
) -> bytes | None:
    """Build DMRE wire packet from inner DMR voice frame. None if ver unsupported (2/3).

    ``extended_layout`` matches legacy send_system: True when config VER > 4 (89-byte
    trailer with source repeater); False when config VER == 4 (85-byte trailer).
    """
    if embedded_ver in (2, 3):
        return None
    ver_byte = embedded_ver.to_bytes(1, "big")
    ts = timestamp_ns.to_bytes(8, "big")
    if extended_layout:
        body = b"".join(
            [
                DMRE,
                dmr_packet[4:11],
                server_id,
                dmr_packet[15:],
                ber,
                rssi,
                ver_byte,
                ts,
                source_server,
                source_rptr,
                hops,
            ]
        )
    else:
        body = b"".join(
            [
                DMRE,
                dmr_packet[4:11],
                server_id,
                dmr_packet[15:],
                ber,
                rssi,
                ver_byte,
                ts,
                source_server,
                hops,
            ]
        )
    hash_len = len(body)
    mac = dmre_blake2b_mac(body, passphrase, hash_len)
    return body + mac
