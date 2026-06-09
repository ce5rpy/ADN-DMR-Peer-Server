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
