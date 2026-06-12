# ADN DMR Peer Server - infrastructure proxy rpto queue
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

"""In-memory pending RPTO queue (Phase 3)."""

from __future__ import annotations

from collections import deque

from adn_server.application.ports import PendingRptoQueue


class InMemoryPendingRptoQueue(PendingRptoQueue):
    """FIFO queue of RPTO payloads keyed by peer_id."""

    def __init__(self) -> None:
        self._items: deque[tuple[bytes, bytes]] = deque()

    def enqueue(self, peer_id: bytes, payload: bytes) -> None:
        self._items.append((peer_id, payload))

    def dequeue(self) -> tuple[bytes, bytes] | None:
        if not self._items:
            return None
        return self._items.popleft()
