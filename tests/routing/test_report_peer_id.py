# ADN DMR Peer Server - tests routing report peer id
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

"""BRDG_EVENT peer_id resolution for RX legs (hotspot transmitting)."""

from __future__ import annotations

from adn_server.application.routing.helpers import resolve_voice_peer_id
from adn_server.domain.value_objects import bytes_3, bytes_4


def test_resolve_voice_peer_uses_rf_src_when_field5_is_network_id() -> None:
    hotspot = bytes_4(730039101)
    systems = {
        "SYSTEM": {
            "PEERS": {
                hotspot: {"CONNECTION": "YES"},
            }
        }
    }
    network_peer = bytes_4(73003)
    resolved = resolve_voice_peer_id(
        network_peer,
        bytes_3(730039101),
        "SYSTEM",
        systems,
    )
    assert resolved == hotspot


def test_resolve_voice_peer_keeps_known_hotspot_id() -> None:
    hotspot = bytes_4(730039102)
    systems = {"SYSTEM": {"PEERS": {hotspot: {"CONNECTION": "YES"}}}}
    resolved = resolve_voice_peer_id(
        hotspot,
        bytes_3(730039102),
        "SYSTEM",
        systems,
    )
    assert resolved == hotspot


def test_resolve_voice_peer_resolves_network_prefix_for_single_hotspot() -> None:
    hotspot = bytes_4(730039101)
    systems = {"SYSTEM": {"PEERS": {hotspot: {"CONNECTION": "YES"}}}}
    resolved = resolve_voice_peer_id(
        bytes_4(73003),
        bytes_3(7300392),
        "SYSTEM",
        systems,
    )
    assert resolved == hotspot
