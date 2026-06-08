"""Immutable mesh wire messages (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PeerMeshConfig:
    """Peer/session parameters for mesh encode and decode."""

    passphrase: bytes
    server_id: bytes
    wire_ver: int | None = None
    embedded_ver: int = 5


@dataclass(frozen=True, slots=True)
class MeshIngress:
    """Verified voice ingress from a remote mesh peer."""

    codec: str
    voice_frame: bytes
    hops: bytes
    ber: bytes
    rssi: bytes
    source_server: bytes
    source_rptr: bytes
    embedded_ver: int | None = None


@dataclass(frozen=True, slots=True)
class MeshEgress:
    """Inner DMR voice packet to wrap for a mesh peer."""

    inner_packet: bytes
    hops: bytes = b"\x01"
    ber: bytes = b"\x00"
    rssi: bytes = b"\x00"
    source_server: bytes = b"\x00\x00\x00\x00"
    source_rptr: bytes = b"\x00\x00\x00\x00"
    timestamp_ns: int | None = None
