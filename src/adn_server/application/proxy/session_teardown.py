# ADN DMR Peer Server - application proxy session teardown
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

"""Wire packets for proxy session teardown (legacy reaper parity)."""

from __future__ import annotations

# Homebrew command prefixes (wire vocabulary; no I/O)
_MSTCL = b"MSTCL"
_RPTCL = b"RPTCL"

CLIENT_TEARDOWN_REPEAT = 3


def master_teardown_packet(peer_id: bytes) -> bytes:
    return _RPTCL + peer_id


def client_teardown_packet() -> bytes:
    return _MSTCL
