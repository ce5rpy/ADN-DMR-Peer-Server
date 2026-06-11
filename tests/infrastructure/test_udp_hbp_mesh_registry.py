"""MeshCodecRegistry wired into HBPProtocol OPENBRIDGE ingress/egress."""

from __future__ import annotations

from adn_server.domain import bytes_4
from adn_server.infrastructure.hbp_constants import DMRD
from adn_server.infrastructure.mesh.obp_v1 import build_dmrd_v1
from adn_server.infrastructure.twisted_adapters.udp_hbp import HBPProtocol

_PASS = b"test-passphrase\x00\x00\x00\x00\x00\x00"
_SERVER = bytes_4(73010)


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


def _obp_protocol() -> HBPProtocol:
    config = {
        "GLOBAL": {"SERVER_ID": _SERVER, "PASSPHRASE": _PASS},
        "SYSTEMS": {
            "OBP-A": {
                "MODE": "OPENBRIDGE",
                "PASSPHRASE": _PASS,
                "VER": 5,
                "TARGET_IP": "127.0.0.1",
                "TARGET_PORT": 62030,
                "NETWORK_ID": _SERVER,
            },
        },
    }
    return HBPProtocol("OBP-A", config)


def test_hbp_decode_mesh_ingress_obp_v1() -> None:
    proto = _obp_protocol()
    inner = _sample_dmr_voice()
    wire = build_dmrd_v1(inner, _SERVER, _PASS)
    ingress = proto._try_decode_mesh_ingress(wire)
    assert ingress is not None
    assert ingress.codec == "obp_v1"
    assert ingress.voice_frame[:4] == DMRD


def test_hbp_encode_mesh_egress_dmre_when_ver_ge_4() -> None:
    proto = _obp_protocol()
    inner = _sample_dmr_voice()
    wire = proto._encode_mesh_egress(
        inner,
        hops=b"\x01",
        ber=b"\x00",
        rssi=b"\x00",
        source_server=_SERVER,
        source_rptr=bytes_4(100),
    )
    assert wire is not None
    assert len(wire) == 89
    assert wire[:4] == b"DMRE"
