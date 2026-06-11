# ADN DMR Peer Server - subscription store authority
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Publish ``SubscriptionStore`` to the legacy ``BRIDGES`` shim for monitor/report."""

from __future__ import annotations

from typing import Any

from ..ports import SubscriptionStore
from ..subscription.bridges_export import export_bridges
from ..subscription.bridges_legacy_view import BridgesLegacyView


class StoreAuthorityMixin:
    """Store authority helpers for ``BridgeUseCases``."""

    _subscription_store: SubscriptionStore
    _router: Any
    _config: dict[str, Any]
    _bridges_legacy_view: BridgesLegacyView | None

    def _bridges_for_report(self) -> dict[str, list[dict[str, Any]]]:
        """BRIDGES snapshot for monitor/report (export shim from subscription store)."""
        view = getattr(self, "_bridges_legacy_view", None)
        if view is None:
            view = BridgesLegacyView(self._subscription_store)
            self._bridges_legacy_view = view
        return view.generate()

    def _export_store_to_router(self) -> None:
        """Push subscription store snapshot to the legacy BRIDGES shim."""
        self._router.set_bridges(export_bridges(self._subscription_store))
        self._router.rebuild_source_index()

    def _finalize_bridges_state(self) -> None:
        """Alias: publish store to router (no direct BRIDGES mutation)."""
        self._export_store_to_router()
