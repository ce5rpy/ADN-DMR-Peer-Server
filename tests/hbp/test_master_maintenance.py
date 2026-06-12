# ADN DMR Peer Server - tests hbp master maintenance
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

"""HBP MASTER maintenance loop (peer timeout / PEERS dict parity)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from adn_server.domain import bytes_4
from adn_server.infrastructure.config_normalizer import ensure_system_runtime_config
from adn_server.infrastructure.twisted_adapters.udp_hbp import HBPProtocol


def _echo_master_config() -> dict:
    config = {
        "GLOBAL": {"PING_TIME": 10, "MAX_MISSED": 3, "USE_ACL": False},
        "SYSTEMS": {
            "ECHO": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 1,
                "OPTIONS": "TS2=9990;",
            }
        },
    }
    ensure_system_runtime_config(config)
    return config


def test_maintenance_timeout_removes_peer_and_sets_reset() -> None:
    """Timed-out peer is removed from PEERS and triggers _reset when last peer leaves."""
    config = _echo_master_config()
    proto = HBPProtocol("ECHO", config)
    proto.transport = MagicMock()
    peer_id = bytes_4(9990)
    proto._peers[peer_id] = {
        "CONNECTION": "YES",
        "LAST_PING": 0,
        "SOCKADDR": ("127.0.0.1", 54915),
        "CALLSIGN": b"ECHO    ",
        "RADIO_ID": "9990",
    }
    assert peer_id in config["SYSTEMS"]["ECHO"]["PEERS"]

    proto._master_maintenance_loop()

    assert peer_id not in proto._peers
    assert peer_id not in config["SYSTEMS"]["ECHO"]["PEERS"]
    assert config["SYSTEMS"]["ECHO"].get("_reset") is True
    proto.transport.write.assert_called_once()


def test_peers_dict_is_shared_with_system_config() -> None:
    """_peers must alias sys_cfg['PEERS'] so login state survives maintenance."""
    config = _echo_master_config()
    del config["SYSTEMS"]["ECHO"]["PEERS"]
    proto = HBPProtocol("ECHO", config)
    peer_id = bytes_4(9990)
    proto._peers[peer_id] = {"LAST_PING": time.time(), "SOCKADDR": ("127.0.0.1", 1)}
    assert peer_id in config["SYSTEMS"]["ECHO"]["PEERS"]
