"""Store-native stat_trimmer_loop (P2-015)."""

from __future__ import annotations

import logging
from collections import defaultdict

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.bridges_export import _legacy_to_type
from adn_server.domain.subscription import Subscription

logger = logging.getLogger(__name__)


def apply_stat_trimmer_store(store: SubscriptionStore) -> None:
    """Remove STAT-only bridge tables with no ON-active or OFF legs in use."""
    by_table: dict[str, list[Subscription]] = defaultdict(list)
    for sub in store.snapshot():
        by_table[sub.table_key()].append(sub)

    for bridge_key, entries in list(by_table.items()):
        has_stat = any(_legacy_to_type(sub) == "STAT" for sub in entries)
        in_use = any(
            (_legacy_to_type(sub) == "ON" and sub.is_active()) or _legacy_to_type(sub) == "OFF"
            for sub in entries
        )
        if has_stat and not in_use:
            for sub in entries:
                store.remove(sub.subscription_id)
            logger.debug("(ROUTER) STAT bridge %s removed", bridge_key)
