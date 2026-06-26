# ADN DMR Peer Server - tests infrastructure peer disconnect report
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

"""Peer disconnect clears internal UA sessions; no synthetic bridge events."""

from __future__ import annotations

from unittest.mock import MagicMock

from adn_server.application.routing.helpers import (
    export_peer_ua_sessions,
    register_peer_ua_session,
)
from adn_server.domain import bytes_4
from adn_server.infrastructure.twisted_adapters.udp_hbp import HBPProtocol


def _master_protocol(*, report: MagicMock | None = None) -> HBPProtocol:
    peer_id = bytes_4(730039101)
    config = {
        "REPORTS": {"REPORT": True},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "PEERS": {
                    peer_id: {
                        "CONNECTION": "YES",
                        "OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;",
                    }
                },
                "_PEER_UA_SESSIONS": {},
            }
        },
    }
    proto = HBPProtocol("SYSTEM", config, report_factory=report)
    proto._peers = config["SYSTEMS"]["SYSTEM"]["PEERS"]
    return proto


def test_disconnect_keeps_sys_cfg_sessions() -> None:
    report = MagicMock()
    proto = _master_protocol(report=report)
    peer_id = bytes_4(730039101)
    sys_cfg = proto._config
    register_peer_ua_session(
        proto._peers[peer_id], peer_id, 2, 7305, sys_cfg, now=1_000_000.0
    )
    assert export_peer_ua_sessions(sys_cfg, peer_id, now=1_000_100.0)

    proto._on_peer_disconnected(peer_id)

    report.send_routing_event.assert_not_called()
    assert export_peer_ua_sessions(sys_cfg, peer_id, now=1_000_100.0)["2"]["tgid"] == 7305


def test_disconnect_clears_peer_voice_slots() -> None:
    proto = _master_protocol()
    peer_id = bytes_4(730039101)
    pk = bytes_4(730039101)
    proto._peer_voice_slots[pk] = {
        2: {"stream_id": bytes_4(0x12345678), "tgid": 7305, "time": 1_000_000.0},
    }
    proto._peer_voice_hangtime[pk] = {2: (7305, 1_000_000.0)}

    proto._on_peer_disconnected(peer_id)

    assert pk not in proto._peer_voice_slots
    assert pk not in proto._peer_voice_hangtime


def test_export_peer_ua_sessions_omits_expired() -> None:
    peer_id = bytes_4(730039101)
    sys_cfg: dict = {"_PEER_UA_SESSIONS": {}}
    register_peer_ua_session(
        {"OPTIONS": b"SINGLE=1;TIMER=5;"}, peer_id, 2, 7305, sys_cfg, now=1_000_000.0
    )
    active = export_peer_ua_sessions(sys_cfg, peer_id, now=1_000_100.0)
    expired = export_peer_ua_sessions(sys_cfg, peer_id, now=9_999_999.0)
    assert active["2"]["tgid"] == 7305
    assert expired == {}
