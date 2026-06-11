"""Import legacy ``BRIDGES`` snapshots into ``SubscriptionStore`` (tests and harness only).

Runtime paths mutate the store directly and publish via ``export_bridges``; they must not
call ``replace_store_from_bridges`` — that would overwrite store authority with the shim.
"""

from __future__ import annotations

from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.bridges_import import subscriptions_from_bridges


def replace_store_from_bridges(
    store: SubscriptionStore,
    bridges: dict[str, list[dict[str, Any]]],
) -> None:
    """Replace store contents from a full ``BRIDGES`` snapshot."""
    store.replace_all(subscriptions_from_bridges(bridges))
