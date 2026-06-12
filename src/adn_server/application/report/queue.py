# ADN DMR Peer Server - application report queue
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

"""Bounded in-process report queue — decouple hot path from TCP encode/send."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..ports import ReportSender

logger = logging.getLogger(__name__)

DEFAULT_MAX_EVENTS = 2048
DEFAULT_MAX_DRAIN_PER_TICK = 128


@dataclass
class BoundedReportQueue:
    """Coalesce config/bridge snapshots; bound voice-event backlog (drop oldest)."""

    max_events: int = DEFAULT_MAX_EVENTS
    max_drain_per_tick: int = DEFAULT_MAX_DRAIN_PER_TICK
    _events: deque[str] = field(default_factory=deque, init=False, repr=False)
    _pending_config: tuple[dict[str, Any], bool] | None = field(default=None, init=False, repr=False)
    _pending_bridge: tuple[dict[str, Any], bool] | None = field(default=None, init=False, repr=False)
    dropped_events: int = field(default=0, init=False)

    def enqueue_event(self, event: str) -> None:
        if len(self._events) >= self.max_events:
            self._events.popleft()
            self.dropped_events += 1
        self._events.append(event)

    def enqueue_config(self, systems: dict[str, Any], *, incremental: bool = False) -> None:
        self._pending_config = (systems, incremental)

    def enqueue_bridge(self, bridges: dict[str, Any], *, incremental: bool = False) -> None:
        self._pending_bridge = (bridges, incremental)

    def pending_count(self) -> int:
        n = len(self._events)
        if self._pending_config is not None:
            n += 1
        if self._pending_bridge is not None:
            n += 1
        return n

    def drain(self, sender: ReportSender) -> int:
        """Flush pending work to ``sender``; at most ``max_drain_per_tick`` voice events per call."""
        sent = 0
        budget = self.max_drain_per_tick
        while self._events and budget > 0:
            sender.send_routing_event(self._events.popleft())
            sent += 1
            budget -= 1
        if self._pending_config is not None:
            systems, incremental = self._pending_config
            self._pending_config = None
            sender.set_systems(systems)
            sender.send_config(systems, incremental=incremental)
            sent += 1
        if self._pending_bridge is not None:
            bridges, incremental = self._pending_bridge
            self._pending_bridge = None
            sender.set_routing_table(bridges)
            sender.send_routing_table(bridges, incremental=incremental)
            sent += 1
        if self.dropped_events and sent:
            logger.debug("(REPORT) queue drained %s item(s); dropped_events=%s", sent, self.dropped_events)
        return sent


class QueuedReportSender(ReportSender):
    """``ReportSender`` port: enqueue only; a reactor worker drains to ``inner``."""

    def __init__(self, queue: BoundedReportQueue, inner: ReportSender) -> None:
        self._queue = queue
        self._inner = inner

    def set_systems(self, systems: dict[str, Any]) -> None:
        self._inner.set_systems(systems)

    def set_routing_table(self, bridges: dict[str, Any]) -> None:
        self._inner.set_routing_table(bridges)

    def send_config(self, systems: dict[str, Any], *, incremental: bool = False) -> None:
        self._inner.set_systems(systems)
        self._queue.enqueue_config(systems, incremental=incremental)

    def send_routing_table(self, bridges: dict[str, Any], *, incremental: bool = False) -> None:
        self._inner.set_routing_table(bridges)
        self._queue.enqueue_bridge(bridges, incremental=incremental)

    def send_routing_event(self, event: str) -> None:
        self._queue.enqueue_event(event)

    @property
    def inner(self) -> ReportSender:
        return self._inner

    @property
    def queue(self) -> BoundedReportQueue:
        return self._queue
