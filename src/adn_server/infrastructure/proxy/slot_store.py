"""In-memory proxy slot store (Phase 3; not wired to UDP yet)."""

from __future__ import annotations

from adn_server.application.ports import ProxySlotStore
from adn_server.domain.proxy import ClientSlot, UpstreamPortRange


class InMemoryProxySlotStore(ProxySlotStore):
    """Track ``ClientSlot`` by peer_id and upstream port occupancy."""

    def __init__(self, port_range: UpstreamPortRange) -> None:
        self._port_range = port_range
        self._by_peer: dict[bytes, ClientSlot] = {}
        self._by_upstream: dict[int, bytes] = {}

    def bind(self, slot: ClientSlot) -> None:
        if slot.upstream_port in self._by_upstream:
            raise ValueError(f"upstream port {slot.upstream_port} already bound")
        if slot.peer_id in self._by_peer:
            raise ValueError("peer_id already bound")
        self._by_peer[slot.peer_id] = slot
        self._by_upstream[slot.upstream_port] = slot.peer_id

    def update_client(self, peer_id: bytes, host: str, port: int) -> None:
        slot = self._by_peer.get(peer_id)
        if slot is None:
            raise KeyError(peer_id)
        self._by_peer[peer_id] = slot.with_client(host, port)

    def unbind(self, peer_id: bytes) -> ClientSlot | None:
        slot = self._by_peer.pop(peer_id, None)
        if slot is None:
            return None
        self._by_upstream.pop(slot.upstream_port, None)
        return slot

    def get_by_peer(self, peer_id: bytes) -> ClientSlot | None:
        return self._by_peer.get(peer_id)

    def get_by_upstream(self, upstream_port: int) -> ClientSlot | None:
        peer_id = self._by_upstream.get(upstream_port)
        if peer_id is None:
            return None
        return self._by_peer.get(peer_id)

    def free_upstream_ports(self) -> tuple[int, ...]:
        return tuple(p for p in self._port_range.ports() if p not in self._by_upstream)

    def list_slots(self) -> tuple[ClientSlot, ...]:
        return tuple(self._by_peer.values())
