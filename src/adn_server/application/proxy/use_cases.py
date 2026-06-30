# ADN DMR Peer Server - application proxy use cases
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

"""ProxyService use cases: client registration, pending RPTO (Phase 3)."""

from __future__ import annotations

import time
from collections.abc import Sequence

from adn_server.application.ports import PendingRptoQueue, ProxyIpBlacklist, ProxySlotStore
from adn_server.domain.errors import DomainError
from adn_server.domain.proxy import ClientEndpoint, ClientSlot, PendingRpto, SessionTeardown
from adn_server.domain.result import Fail, Result, Success
from adn_server.domain.value_objects import int_id


class ProxySlotError(DomainError):
    """Proxy session allocation or lookup failure."""


class ProxyUseCases:
    """Register hotspot clients and queue RPTO for the master (in-process inject)."""

    def __init__(
        self,
        slot_store: ProxySlotStore,
        rpto_queue: PendingRptoQueue,
        *,
        max_peers: int = 1,
        black_list: Sequence[int] = (),
        ip_blacklist: ProxyIpBlacklist | None = None,
    ) -> None:
        self._slots = slot_store
        self._rpto_queue = rpto_queue
        self._max_peers = max_peers
        self._black_list = frozenset(black_list)
        self._ip_blacklist = ip_blacklist

    def _allocate_report_slot(self) -> int | None:
        """Lowest free upstream slot index (legacy adn-proxy ``connTrack`` port pool)."""
        used = {
            slot.report_slot
            for slot in self._slots.list_slots()
            if slot.report_slot is not None
        }
        for index in range(self._max_peers):
            if index not in used:
                return index
        return None

    def attach_client(
        self,
        peer_id: bytes,
        host: str,
        port: int,
    ) -> Result[ClientSlot, ProxySlotError]:
        """Bind or refresh a hotspot session (legacy ``peer_track`` on client packet)."""
        if len(peer_id) != 4:
            return Fail(ProxySlotError("peer_id must be 4 bytes"))
        if self.is_ip_blocked(host):
            return Fail(ProxySlotError("client IP is blacklisted"))
        existing = self._slots.get_by_peer(peer_id)
        if existing is not None:
            updated = existing.with_client(host, port)
            self._slots.update_client(peer_id, host, port)
            return Success(updated)
        if int_id(peer_id) in self._black_list:
            return Fail(ProxySlotError("peer is blacklisted"))
        if len(self._slots.list_slots()) >= self._max_peers:
            return Fail(ProxySlotError("maximum peers exceeded"))
        report_slot = self._allocate_report_slot()
        slot = ClientSlot(
            peer_id=peer_id,
            client=ClientEndpoint(host=host, port=port),
            report_slot=report_slot,
        )
        self._slots.bind(slot)
        return Success(slot)

    def detach_client(self, peer_id: bytes) -> ClientSlot | None:
        """Release session (legacy ``reaper`` slot drop without I/O)."""
        return self._slots.unbind(peer_id)

    def expire_session(self, peer_id: bytes) -> SessionTeardown | None:
        """End session and return teardown plan for infrastructure I/O (legacy ``reaper``)."""
        slot = self.detach_client(peer_id)
        if slot is None:
            return None
        return SessionTeardown(peer_id=slot.peer_id, client=slot.client)

    def is_ip_blocked(self, host: str, now: float | None = None) -> bool:
        if self._ip_blacklist is None:
            return False
        return self._ip_blacklist.is_blocked(host, now if now is not None else time.time())

    def block_ip_until(self, host: str, expire_at: float) -> None:
        if self._ip_blacklist is not None:
            self._ip_blacklist.block_until(host, expire_at)

    def block_ip_from_prbl(
        self,
        data: bytes,
        host: str,
        *,
        default_ttl: float = 300,
        now: float | None = None,
    ) -> float:
        """Parse PRBL expiry and block client IP (legacy ``proxy`` PRBL handler)."""
        ts = now if now is not None else time.time()
        expire = ts + default_ttl
        if len(data) > 8:
            try:
                expire = float(data[8:].decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                pass
        self.block_ip_until(host, expire)
        return expire

    def resolve_client(self, peer_id: bytes) -> ClientEndpoint | None:
        """Client endpoint for a connected peer."""
        slot = self._slots.get_by_peer(peer_id)
        return slot.client if slot else None

    def list_slots(self) -> tuple[ClientSlot, ...]:
        return self._slots.list_slots()

    def apply_runtime_settings(
        self,
        *,
        max_peers: int,
        black_list: Sequence[int],
    ) -> None:
        """Hot-reload proxy limits without dropping active sessions."""
        self._max_peers = max_peers
        self._black_list = frozenset(black_list)
