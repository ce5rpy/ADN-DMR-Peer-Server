# ADN DMR Peer Server - subscription store authority
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""``SubscriptionStore`` is the sole runtime routing authority; monitor uses export shim only."""

from __future__ import annotations

from typing import Any

from ..ports import SubscriptionStore
from ..subscription.routing_table_legacy_view import RoutingTableLegacyView


class StoreAuthorityMixin:
    """Store authority helpers for ``RoutingUseCases``."""

    _subscription_store: SubscriptionStore
    _config: dict[str, Any]
    _routing_table_legacy_view: RoutingTableLegacyView | None

    def _routing_table_for_report(self) -> dict[str, list[dict[str, Any]]]:
        """BRIDGES snapshot for monitor/report only (export shim, not routing authority)."""
        view = getattr(self, "_routing_table_legacy_view", None)
        if view is None:
            view = RoutingTableLegacyView(self._subscription_store)
            self._routing_table_legacy_view = view
        return view.generate()

    def _sync_subscription_store(self) -> None:
        """No-op: runtime state lives only in ``SubscriptionStore`` (D-08)."""

    def _finalize_routing_state(self) -> None:
        """No-op kept for harness/tests; routing reads ``SubscriptionStore`` only."""
