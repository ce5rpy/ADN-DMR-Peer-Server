# ADN DMR Peer Server - domain HBP protocol helpers
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

from __future__ import annotations

from adn_server.domain.hbp_protocol import (
    normalize_fixed_width_ascii,
    normalize_fixed_width_bytes,
)


def test_normalize_fixed_width_ascii_strips_nul_and_space() -> None:
    assert normalize_fixed_width_ascii(b"CE5RPY\x00\x00") == "CE5RPY"
    assert normalize_fixed_width_ascii(b"CE5RPY  ") == "CE5RPY"
    assert normalize_fixed_width_ascii("Bridge\x00 ") == "Bridge"


def test_normalize_fixed_width_bytes_strips_nul_and_space() -> None:
    raw = b"TS1=730;TS2=73081" + b"\x00" * 8 + b"  "
    assert normalize_fixed_width_bytes(raw) == b"TS1=730;TS2=73081"
