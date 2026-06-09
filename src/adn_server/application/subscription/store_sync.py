"""Keep ``SubscriptionStore`` aligned with legacy ``BRIDGES`` (read-only mirror; not routing authority yet)."""

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
