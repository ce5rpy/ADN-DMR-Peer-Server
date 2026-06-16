# ADN DMR Peer Server - infrastructure twisted adapters report opcodes
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

"""TCP report channel opcodes (shared by all wire encoders)."""

from __future__ import annotations

REPORT_OPCODES = {
    "CONFIG_REQ": b"\x00",
    "CONFIG_SND": b"\x01",
    "BRIDGE_REQ": b"\x02",
    "BRIDGE_SND": b"\x03",
    "CONFIG_UPD": b"\x04",
    "BRIDGE_UPD": b"\x05",
    "LINK_EVENT": b"\x06",
    "BRDG_EVENT": b"\x07",
    "TOPOLOGY_SND": b"\x10",
    "ROUTING_TABLE_SND": b"\x11",
    "VOICE_EVENT_SND": b"\x12",
    "DELTA_SND": b"\x13",
    "STATE_SND": b"\x14",
    "STATE_REQ": b"\x15",
    "HELLO": b"\xff",
}

SERVER_NAME = "adn-server"


def server_version() -> str:
    """Package version for HELLO (same source as ``adn_server --version``)."""
    from adn_server import __version__

    return __version__
