# ADN DMR Peer Server - tests infrastructure hbp auth handshake
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

"""Full HBP login exchange on MASTER (RPTL → RPTK → RPTC)."""

from __future__ import annotations

from adn_server.domain.value_objects import bytes_4
from adn_server.infrastructure.config_normalizer import ensure_system_runtime_config
from adn_server.infrastructure.hbp_constants import MSTNAK, RPTACK, RPTC, RPTK, RPTL
from adn_server.infrastructure.twisted_adapters.udp_hbp import (
    HBPProtocol,
    _calc_hash,
    _get_passphrase_bytes,
)

_PEER = bytes_4(1234567)
_CLIENT_ADDR = ("192.168.1.50", 62031)
_PASSPHRASE = b"test-passphrase"


class _RecordingTransport:
    def __init__(self) -> None:
        self.sent: list[tuple[bytes, tuple[str, int]]] = []

    def write(self, data: bytes, addr: tuple[str, int]) -> None:
        self.sent.append((data, addr))


class _AclRouter:
    def acl_check(self, peer_id: bytes, acl: object) -> bool:
        return True


def _build_rptc(peer: bytes) -> bytes:
    return RPTC + peer + b"CE1TEST " + b"\x00" * 85 + b"4"


def _master_protocol(*, passphrase: bytes = _PASSPHRASE) -> tuple[HBPProtocol, _RecordingTransport]:
    transport = _RecordingTransport()
    config = {
        "GLOBAL": {"PING_TIME": 10, "MAX_MISSED": 3, "USE_ACL": False},
        "SYSTEMS": {
            "HOTSPOT": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 8,
                "PASSPHRASE": passphrase,
                "OPTIONS": "TS2=9990;",
            }
        },
    }
    ensure_system_runtime_config(config)
    hbp = HBPProtocol("HOTSPOT", config, router=_AclRouter())  # type: ignore[arg-type]
    hbp.transport = transport  # type: ignore[assignment]
    return hbp, transport


def test_hbp_auth_handshake_rptl_rptk_rptc() -> None:
    hbp, transport = _master_protocol()
    hbp.datagramReceived(RPTL + _PEER, _CLIENT_ADDR)

    assert len(transport.sent) == 1
    challenge, addr = transport.sent[0]
    assert challenge.startswith(RPTACK)
    assert addr == _CLIENT_ADDR
    assert hbp._peers[_PEER]["CONNECTION"] == "CHALLENGE_SENT"

    salt_str = bytes_4(hbp._peers[_PEER]["SALT"])
    sys_cfg = hbp._config
    auth_hash = _calc_hash(salt_str, _get_passphrase_bytes(sys_cfg))
    transport.sent.clear()

    hbp.datagramReceived(RPTK + _PEER + auth_hash, _CLIENT_ADDR)
    assert len(transport.sent) == 1
    rptk_ack, addr = transport.sent[0]
    assert rptk_ack.startswith(RPTACK)
    assert addr == _CLIENT_ADDR
    assert hbp._peers[_PEER]["CONNECTION"] == "WAITING_CONFIG"

    transport.sent.clear()
    hbp.datagramReceived(_build_rptc(_PEER), _CLIENT_ADDR)
    assert len(transport.sent) == 1
    rptc_ack, addr = transport.sent[0]
    assert rptc_ack.startswith(RPTACK)
    assert addr == _CLIENT_ADDR
    assert hbp._peers[_PEER]["CONNECTION"] == "YES"


def test_hbp_auth_wrong_password_mstnak() -> None:
    hbp, transport = _master_protocol()
    hbp.datagramReceived(RPTL + _PEER, _CLIENT_ADDR)
    salt_str = bytes_4(hbp._peers[_PEER]["SALT"])
    bad_hash = _calc_hash(salt_str, b"wrong-password")
    transport.sent.clear()

    hbp.datagramReceived(RPTK + _PEER + bad_hash, _CLIENT_ADDR)

    assert len(transport.sent) == 1
    nak, addr = transport.sent[0]
    assert nak.startswith(MSTNAK)
    assert addr == _CLIENT_ADDR
    assert _PEER not in hbp._peers


def _auth_to_waiting_config(hbp: HBPProtocol, transport: _RecordingTransport) -> None:
    hbp.datagramReceived(RPTL + _PEER, _CLIENT_ADDR)
    salt_str = bytes_4(hbp._peers[_PEER]["SALT"])
    auth_hash = _calc_hash(salt_str, _get_passphrase_bytes(hbp._config))
    transport.sent.clear()
    hbp.datagramReceived(RPTK + _PEER + auth_hash, _CLIENT_ADDR)
    transport.sent.clear()


def test_rptc_accepts_nul_padded_callsign_with_allow_unreg_false() -> None:
    """RPTC callsign fields may be NUL-padded (ipsc2hbp); must match DB like space pad."""
    hbp, transport = _master_protocol()
    hbp._config["ALLOW_UNREG_ID"] = False
    hbp._CONFIG["_SUB_IDS"] = {1234567: "Bridge"}
    _auth_to_waiting_config(hbp, transport)

    # 8-byte field: "Bridge" + two NUL pads (not spaces)
    rptc = RPTC + _PEER + b"Bridge\x00\x00" + b"\x00" * 85 + b"4"
    hbp.datagramReceived(rptc, _CLIENT_ADDR)

    assert len(transport.sent) == 1
    assert transport.sent[0][0].startswith(RPTACK)
    assert hbp._peers[_PEER]["CONNECTION"] == "YES"


def test_rptc_rejects_wrong_callsign_with_allow_unreg_false() -> None:
    hbp, transport = _master_protocol()
    hbp._config["ALLOW_UNREG_ID"] = False
    hbp._CONFIG["_SUB_IDS"] = {1234567: "Bridge"}
    _auth_to_waiting_config(hbp, transport)

    rptc = RPTC + _PEER + b"WRONG   " + b"\x00" * 85 + b"4"
    hbp.datagramReceived(rptc, _CLIENT_ADDR)

    assert len(transport.sent) == 1
    assert transport.sent[0][0].startswith(MSTNAK)
    assert _PEER not in hbp._peers
