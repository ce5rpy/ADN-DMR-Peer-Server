"""Import legacy ``BRIDGES`` snapshots into ``SubscriptionStore``.

Runtime hot paths mutate the store directly and publish via ``export_routing_table``; they must not
call ``replace_store_from_routing_table`` (would overwrite store authority with the shim).
Bootstrap and tests may import once — e.g. ``_seed_echo_routing_table`` in ``peer_server.py``.
"""

from __future__ import annotations

from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.routing_table_import import subscriptions_from_routing_table


def replace_store_from_routing_table(
    store: SubscriptionStore,
    bridges: dict[str, list[dict[str, Any]]],
) -> None:
    """Replace store contents from a full ``BRIDGES`` snapshot."""
    store.replace_all(subscriptions_from_routing_table(bridges))
