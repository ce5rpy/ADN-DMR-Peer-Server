"""Legacy BRIDGES view from ``SubscriptionStore`` (v1 monitor shim, D-08)."""

from __future__ import annotations

from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.routing_table_export import export_routing_table


class RoutingTableLegacyView:
    """One-way export: subscriptions → legacy ``BRIDGES`` dict (pickle / ``BRIDGE_SND``)."""

    def __init__(self, store: SubscriptionStore) -> None:
        self._store = store

    def generate(self, *, now: float | None = None) -> dict[str, list[dict[str, Any]]]:
        """Build a pickle-compatible ``BRIDGES`` snapshot (legacy ``bridge_master.send_routing_table``)."""
        return export_routing_table(self._store, now=now)
