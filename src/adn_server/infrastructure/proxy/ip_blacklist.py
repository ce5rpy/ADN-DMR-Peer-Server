# ADN DMR Peer Server - infrastructure proxy ip blacklist
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

"""In-memory IP blacklist for proxy fan-in."""

from __future__ import annotations

from adn_server.application.ports import ProxyIpBlacklist


class InMemoryProxyIpBlacklist(ProxyIpBlacklist):
    def __init__(self, initial: dict[str, float] | None = None) -> None:
        self._entries: dict[str, float] = dict(initial or {})

    def block_until(self, host: str, expire_at: float) -> None:
        self._entries[host] = expire_at

    def is_blocked(self, host: str, now: float) -> bool:
        expire = self._entries.get(host)
        return expire is not None and now < expire

    def merge_static_entries(self, entries: dict[str, float]) -> None:
        """Apply config IP_BLACK_LIST entries (runtime PRBL blocks are kept)."""
        self._entries.update(entries)
