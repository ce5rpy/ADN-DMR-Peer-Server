# ADN DMR Peer Server - subscription store authority (V2-P2-010 / P2-011)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Keep ``SubscriptionStore`` and legacy ``BRIDGES`` aligned after routing mutations."""

from __future__ import annotations

from typing import Any

from ..subscription.bridges_export import export_bridges
from ..subscription.bridges_legacy_view import BridgesLegacyView
from ..subscription.store_sync import replace_store_from_bridges


class StoreAuthorityMixin:
    """Store mirror / authority helpers for ``BridgeUseCases``."""

    _subscription_store: Any
    _router: Any
    _config: dict[str, Any]
    _bridges_legacy_view: BridgesLegacyView | None

    def _use_subscription_store_authority(self) -> bool:
        if self._subscription_store is None:
            return False
        return bool(self._config.get("GLOBAL", {}).get("USE_SUBSCRIPTION_STORE_AUTHORITY", False))

    def _bridges_for_report(self) -> dict[str, list[dict[str, Any]]]:
        """BRIDGES snapshot for monitor/report (export shim when store authority is on)."""
        if self._subscription_store is not None and self._use_subscription_store_authority():
            view = getattr(self, "_bridges_legacy_view", None)
            if view is None:
                view = BridgesLegacyView(self._subscription_store)
                self._bridges_legacy_view = view
            return view.generate()
        return self._router.get_bridges()

    def _sync_store_for_voice_lookup(self) -> None:
        """Import router BRIDGES into the store (e.g. OBP ``_ensure_obp_source_for_tg``) before resolve."""
        replace_store_from_bridges(self._subscription_store, self._router.get_bridges())
        if self._use_subscription_store_authority():
            self._router.set_bridges(export_bridges(self._subscription_store))
        self._router.rebuild_source_index()

    def _finalize_bridges_state(self) -> None:
        """Import BRIDGES mutations into the store; export back when store is authority."""
        if self._subscription_store is None:
            self._router.rebuild_source_index()
            return
        self._sync_store_for_voice_lookup()
