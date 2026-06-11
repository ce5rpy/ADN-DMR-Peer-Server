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
