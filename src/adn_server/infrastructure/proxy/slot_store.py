# ADN DMR Peer Server - infrastructure proxy slot store
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

"""In-memory proxy slot store (Phase 3)."""

from __future__ import annotations

from adn_server.application.ports import ProxySlotStore
from adn_server.domain.proxy import ClientSlot


class InMemoryProxySlotStore(ProxySlotStore):
    """Track ``ClientSlot`` by peer_id."""

    def __init__(self) -> None:
        self._by_peer: dict[bytes, ClientSlot] = {}

    def bind(self, slot: ClientSlot) -> None:
        if slot.peer_id in self._by_peer:
            raise ValueError("peer_id already bound")
        self._by_peer[slot.peer_id] = slot

    def update_client(self, peer_id: bytes, host: str, port: int) -> None:
        slot = self._by_peer.get(peer_id)
        if slot is None:
            raise KeyError(peer_id)
        self._by_peer[peer_id] = slot.with_client(host, port)

    def unbind(self, peer_id: bytes) -> ClientSlot | None:
        return self._by_peer.pop(peer_id, None)

    def get_by_peer(self, peer_id: bytes) -> ClientSlot | None:
        return self._by_peer.get(peer_id)

    def list_slots(self) -> tuple[ClientSlot, ...]:
        return tuple(self._by_peer.values())
