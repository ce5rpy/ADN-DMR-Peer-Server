# ADN DMR Peer Server - subscription store authority
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
#
# Derived from ADN DMR Server / FreeDMR / HBlink. Original license:
###############################################################################
# Copyright (C) 2026 Joaquin Madrid Belando, EA5GVK <ea5gvk@gmail.com>
# Copyright (C) 2020 Simon Adlem, G7RZU <g7rzu@gb7fr.org.uk>
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS <n0mjs@me.com>
#
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
