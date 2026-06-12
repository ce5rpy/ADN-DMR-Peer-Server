# ADN DMR Peer Server - infrastructure proxy reply transport
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

"""Route MASTER HBP replies through the proxy fan-in UDP socket."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from adn_server.infrastructure.hbp_constants import PRBL


class _DatagramWriter(Protocol):
    def write(self, data: bytes, addr: tuple[str, int]) -> None:
        ...


class ProxyReplyTransport:
    """Wrap the fan-in transport so MASTER replies leave via LISTEN_PORT."""

    def __init__(
        self,
        fanin_transport: _DatagramWriter,
        *,
        prbl_handler: Callable[[bytes, tuple[str, int]], None] | None = None,
    ) -> None:
        self._fanin = fanin_transport
        self._prbl_handler = prbl_handler

    def write(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) >= 4 and data[:4] == PRBL and self._prbl_handler is not None:
            self._prbl_handler(data, addr)
            return
        self._fanin.write(data, addr)
