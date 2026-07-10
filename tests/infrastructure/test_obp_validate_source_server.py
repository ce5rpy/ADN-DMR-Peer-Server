# ADN DMR Peer Server - tests infrastructure obp validate source server
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

"""OBP DMRE source-server validation must not use HBP ALLOW_UNREG_ID bypass."""

from __future__ import annotations

from adn_server.domain import bytes_4
from adn_server.infrastructure.twisted_adapters.udp_hbp import HBPProtocol

_UNKNOWN = bytes_4(3120999)
_KNOWN = bytes_4(3120001)


def _obp_protocol(*, allow_unreg: bool | None = None) -> HBPProtocol:
    system = {
        "MODE": "OPENBRIDGE",
        "PASSPHRASE": b"test-passphrase\x00\x00\x00\x00\x00\x00",
        "VER": 5,
        "TARGET_IP": "127.0.0.1",
        "TARGET_PORT": 62030,
        "NETWORK_ID": bytes_4(73010),
    }
    if allow_unreg is not None:
        system["ALLOW_UNREG_ID"] = allow_unreg
    config = {
        "GLOBAL": {"SERVER_ID": bytes_4(73010)},
        "_SUB_IDS": {3120001: "CE1TST"},
        "SYSTEMS": {"OBP-A": system},
    }
    return HBPProtocol("OBP-A", config)


def test_obp_source_server_rejects_unknown_even_without_allow_unreg_id() -> None:
    proto = _obp_protocol()
    assert proto.validate_id(_UNKNOWN) is True
    assert proto.validate_obp_source_server_id(_UNKNOWN) is False


def test_obp_source_server_accepts_known_subscriber_id() -> None:
    proto = _obp_protocol()
    assert proto.validate_obp_source_server_id(_KNOWN) == "CE1TST"


def test_obp_source_server_still_rejects_when_allow_unreg_disabled() -> None:
    proto = _obp_protocol(allow_unreg=False)
    assert proto.validate_id(_UNKNOWN) is False
    assert proto.validate_obp_source_server_id(_UNKNOWN) is False
