"""MeshCodecRegistry: auto decode and encode codec selection (P2-005)."""

from __future__ import annotations

from adn_server.domain import bytes_4
from adn_server.domain.hbp_protocol import VER
from adn_server.domain.mesh_routing import MeshEgress, PeerMeshConfig
from adn_server.infrastructure.hbp_constants import DMRD
from adn_server.infrastructure.mesh.dmre_v5 import build_dmre
from adn_server.infrastructure.mesh.obp_v1 import build_dmrd_v1
from adn_server.infrastructure.mesh.registry import MeshCodecRegistry

_PASS = b"test-passphrase\x00\x00\x00\x00\x00\x00"
_SERVER = bytes_4(9990)


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


def _config(*, wire_ver: int | None = None) -> PeerMeshConfig:
    return PeerMeshConfig(passphrase=_PASS, server_id=_SERVER, wire_ver=wire_ver, embedded_ver=VER)


def test_decode_auto_dmre_v5():
    inner = _sample_dmr_voice()
    wire = build_dmre(
        inner,
        server_id=_SERVER,
        ber=b"\x00",
        rssi=b"\x00",
        embedded_ver=VER,
        timestamp_ns=1_700_000_000_000_000_000,
        source_server=_SERVER,
        source_rptr=bytes_4(100),
        hops=b"\x01",
        passphrase=_PASS,
        extended_layout=True,
    )
    assert wire is not None
    ingress = MeshCodecRegistry().decode_auto(wire, _config())
    assert ingress is not None
    assert ingress.codec == "dmre_v5"
    assert ingress.voice_frame[:4] == b"DMRE"
    assert ingress.hops == b"\x01"


def test_decode_auto_obp_v1():
    inner = _sample_dmr_voice()
    wire = build_dmrd_v1(inner, _SERVER, _PASS)
    ingress = MeshCodecRegistry().decode_auto(wire, _config())
    assert ingress is not None
    assert ingress.codec == "obp_v1"
    assert len(ingress.voice_frame) == 53


def test_encode_auto_uses_dmre_when_wire_ver_ge_4():
    registry = MeshCodecRegistry()
    inner = _sample_dmr_voice()
    egress = MeshEgress(inner_packet=inner, timestamp_ns=1_700_000_000_000_000_000)
    wire = registry.encode("auto", egress, _config(wire_ver=5))
    assert wire is not None
    assert len(wire) == 89
    assert registry.resolve_encode_codec("auto", _config(wire_ver=5)) == "dmre_v5"


def test_encode_auto_uses_obp_v1_when_wire_ver_low():
    registry = MeshCodecRegistry()
    inner = _sample_dmr_voice()
    egress = MeshEgress(inner_packet=inner)
    wire = registry.encode("auto", egress, _config(wire_ver=1))
    assert wire is not None
    assert len(wire) == 73
    assert registry.resolve_encode_codec("auto", _config(wire_ver=1)) == "obp_v1"
    assert registry.encode("obp_v1", egress, _config(wire_ver=5)) == wire


def test_encode_auto_honours_session_codec():
    registry = MeshCodecRegistry()
    assert registry.resolve_encode_codec("auto", _config(wire_ver=5), session_codec="obp_v1") == "obp_v1"
