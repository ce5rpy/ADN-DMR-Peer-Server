"""Unit tests for bounded report queue and queued sender."""

from __future__ import annotations

from typing import Any

from adn_server.application.report.queue import BoundedReportQueue, QueuedReportSender


class RecordingSender:
    def __init__(self) -> None:
        self.systems: dict[str, Any] | None = None
        self.routing_table: dict[str, Any] | None = None
        self.config_calls: list[tuple[dict, bool]] = []
        self.routing_table_calls: list[tuple[dict, bool]] = []
        self.events: list[str] = []

    def set_systems(self, systems: dict[str, Any]) -> None:
        self.systems = systems

    def set_routing_table(self, bridges: dict[str, Any]) -> None:
        self.routing_table = bridges

    def send_config(self, systems: dict[str, Any], *, incremental: bool = False) -> None:
        self.config_calls.append((systems, incremental))

    def send_routing_table(self, bridges: dict[str, Any], *, incremental: bool = False) -> None:
        self.routing_table_calls.append((bridges, incremental))

    def send_routing_event(self, event: str) -> None:
        self.events.append(event)


def test_enqueue_event_is_non_blocking():
    inner = RecordingSender()
    queue = BoundedReportQueue(max_events=4, max_drain_per_tick=10)
    sender = QueuedReportSender(queue, inner)
    sender.send_routing_event("GROUP VOICE,START,RX,SYS,1,2,3,1,4")
    assert inner.events == []
    assert queue.pending_count() == 1


def test_drain_delivers_events_before_snapshots():
    inner = RecordingSender()
    queue = BoundedReportQueue(max_drain_per_tick=10)
    sender = QueuedReportSender(queue, inner)
    sender.send_routing_event("e1")
    sender.send_config({"SYS": {}}, incremental=True)
    sender.send_routing_table({"99": []}, incremental=False)
    queue.drain(inner)
    assert inner.events == ["e1"]
    assert len(inner.config_calls) == 1
    assert inner.config_calls[0][1] is True
    assert len(inner.routing_table_calls) == 1


def test_config_and_bridge_coalesce_to_latest():
    inner = RecordingSender()
    queue = BoundedReportQueue()
    sender = QueuedReportSender(queue, inner)
    sender.send_config({"A": 1})
    sender.send_config({"B": 2}, incremental=True)
    sender.send_routing_table({"old": []})
    sender.send_routing_table({"new": []}, incremental=True)
    queue.drain(inner)
    assert inner.config_calls == [({"B": 2}, True)]
    assert inner.routing_table_calls == [({"new": []}, True)]


def test_bounded_queue_drops_oldest_events():
    inner = RecordingSender()
    queue = BoundedReportQueue(max_events=2, max_drain_per_tick=10)
    sender = QueuedReportSender(queue, inner)
    sender.send_routing_event("e1")
    sender.send_routing_event("e2")
    sender.send_routing_event("e3")
    assert queue.dropped_events == 1
    queue.drain(inner)
    assert inner.events == ["e2", "e3"]


def test_drain_respects_per_tick_budget():
    inner = RecordingSender()
    queue = BoundedReportQueue(max_drain_per_tick=2)
    sender = QueuedReportSender(queue, inner)
    for i in range(5):
        sender.send_routing_event(f"e{i}")
    queue.drain(inner)
    assert inner.events == ["e0", "e1"]
    queue.drain(inner)
    assert inner.events == ["e0", "e1", "e2", "e3"]
