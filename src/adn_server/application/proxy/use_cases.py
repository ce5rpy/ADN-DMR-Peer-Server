"""ProxyService use cases: client registration, upstream routing, pending RPTO (Phase 3)."""

from __future__ import annotations

import random
from collections.abc import Sequence

from adn_server.application.ports import PendingRptoQueue, ProxySlotStore
from adn_server.domain.errors import DomainError
from adn_server.domain.proxy import ClientEndpoint, ClientSlot, PendingRpto, UpstreamPortRange
from adn_server.domain.result import Fail, Result, Success
from adn_server.domain.value_objects import int_id


class ProxySlotError(DomainError):
    """Proxy session allocation or lookup failure."""


class ProxyUseCases:
    """Register hotspot clients, map them to upstream ports, queue RPTO for the master."""

    def __init__(
        self,
        slot_store: ProxySlotStore,
        port_range: UpstreamPortRange,
        rpto_queue: PendingRptoQueue,
        *,
        black_list: Sequence[int] = (),
        rng: random.Random | None = None,
    ) -> None:
        self._slots = slot_store
        self._port_range = port_range
        self._rpto_queue = rpto_queue
        self._black_list = frozenset(black_list)
        self._rng = rng or random.Random()

    def attach_client(
        self,
        peer_id: bytes,
        host: str,
        port: int,
    ) -> Result[ClientSlot, ProxySlotError]:
        """Bind or refresh a hotspot session (legacy ``peer_track`` on client packet)."""
        if len(peer_id) != 4:
            return Fail(ProxySlotError("peer_id must be 4 bytes"))
        existing = self._slots.get_by_peer(peer_id)
        if existing is not None:
            updated = existing.with_client(host, port)
            self._slots.update_client(peer_id, host, port)
            return Success(updated)
        if int_id(peer_id) in self._black_list:
            return Fail(ProxySlotError("peer is blacklisted"))
        upstream_port = self._pick_upstream_port()
        if upstream_port is None:
            return Fail(ProxySlotError("no upstream ports available"))
        slot = ClientSlot(
            peer_id=peer_id,
            client=ClientEndpoint(host=host, port=port),
            upstream_port=upstream_port,
        )
        self._slots.bind(slot)
        return Success(slot)

    def detach_client(self, peer_id: bytes) -> ClientSlot | None:
        """Release session and upstream port (legacy ``reaper`` without I/O side effects)."""
        return self._slots.unbind(peer_id)

    def resolve_upstream(self, peer_id: bytes) -> int | None:
        """Upstream port for forwarding client → master."""
        slot = self._slots.get_by_peer(peer_id)
        return slot.upstream_port if slot else None

    def resolve_client(self, upstream_port: int) -> ClientEndpoint | None:
        """Client endpoint for forwarding master → hotspot."""
        slot = self._slots.get_by_upstream(upstream_port)
        return slot.client if slot else None

    def schedule_rpto(self, peer_id: bytes, payload: bytes) -> bool:
        """Queue RPTO body for a connected peer (self-service / login options)."""
        slot = self._slots.get_by_peer(peer_id)
        if slot is None:
            return False
        self._rpto_queue.enqueue(peer_id, payload)
        return True

    def next_pending_rpto(self) -> PendingRpto | None:
        """Dequeue one pending RPTO with its upstream port (for master send loop)."""
        item = self._rpto_queue.dequeue()
        if item is None:
            return None
        peer_id, payload = item
        slot = self._slots.get_by_peer(peer_id)
        if slot is None:
            return None
        return PendingRpto(peer_id=peer_id, payload=payload, upstream_port=slot.upstream_port)

    def list_slots(self) -> tuple[ClientSlot, ...]:
        return self._slots.list_slots()

    def _pick_upstream_port(self) -> int | None:
        free = self._slots.free_upstream_ports()
        if not free:
            return None
        return self._rng.choice(free)
