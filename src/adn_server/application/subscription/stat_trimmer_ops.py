# ADN DMR Peer Server - application subscription stat trimmer ops
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

"""Store-native stat_trimmer_loop."""

from __future__ import annotations

import logging
from collections import defaultdict

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.routing_table_export import _legacy_to_type
from adn_server.domain.subscription import Subscription

logger = logging.getLogger(__name__)


def apply_stat_trimmer_store(store: SubscriptionStore) -> None:
    """Remove STAT-only bridge tables with no ON-active or OFF legs in use."""
    by_table: dict[str, list[Subscription]] = defaultdict(list)
    for sub in store.snapshot():
        by_table[sub.table_key()].append(sub)

    for relay_table_key, entries in list(by_table.items()):
        has_stat = any(_legacy_to_type(sub) == "STAT" for sub in entries)
        has_active_stat_source = any(
            _legacy_to_type(sub) == "STAT" and sub.is_active() for sub in entries
        )
        in_use = any(
            (_legacy_to_type(sub) == "ON" and sub.is_active()) or _legacy_to_type(sub) == "OFF"
            for sub in entries
        )
        # Keep OBP STAT tables while the source leg is active; SYSTEM targets may be OFF/idle
        # until OPTIONS/static TG apply (legacy statTrimmer did not drop mid-QSO OBP bridges).
        if has_stat and has_active_stat_source:
            continue
        if has_stat and not in_use:
            for sub in entries:
                store.remove(sub.subscription_id)
            logger.debug("(ROUTER) STAT bridge %s removed", relay_table_key)
