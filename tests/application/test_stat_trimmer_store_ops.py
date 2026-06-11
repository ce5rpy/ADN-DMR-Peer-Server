"""stat_trimmer must not drop OBP STAT bridges while the source leg is active."""

from __future__ import annotations

from adn_server.application.subscription.subscription_table_ops import ensure_stat_relay_store
from adn_server.application.subscription.stat_trimmer_ops import apply_stat_trimmer_store
from adn_server.application.subscription.subscription_queries import store_has_table
from adn_server.domain import bytes_3
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def test_stat_trimmer_keeps_obp_stat_bridge_with_inactive_system_legs() -> None:
    store = InMemorySubscriptionStore()
    systems_cfg = {
        "OBP-CL": {"MODE": "OPENBRIDGE", "DEFAULT_UA_TIMER": 10},
        "SYSTEM": {"MODE": "MASTER", "DEFAULT_UA_TIMER": 10},
    }
    ensure_stat_relay_store(store, bytes_3(52090), systems_cfg, now=1000.0)
    assert store_has_table(store, "52090")

    apply_stat_trimmer_store(store)

    assert store_has_table(store, "52090")
