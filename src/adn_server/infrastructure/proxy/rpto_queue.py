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
