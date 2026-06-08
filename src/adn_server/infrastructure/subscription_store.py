"""In-memory subscription store (Phase 2 authority; not wired to BRIDGES yet)."""

from __future__ import annotations

from collections.abc import Sequence

from adn_server.application.ports import SubscriptionStore
from adn_server.domain.subscription import (
    AudioChannel,
    Subscription,
    SubscriptionId,
    SubscriptionPhase,
    SystemId,
)


class InMemorySubscriptionStore(SubscriptionStore):
    """Hold subscriptions keyed by ``SubscriptionId``; no Twisted or YAML."""

    def __init__(self) -> None:
        self._items: dict[SubscriptionId, Subscription] = {}

    def get(self, sub_id: SubscriptionId) -> Subscription | None:
        return self._items.get(sub_id)

    def upsert(self, subscription: Subscription) -> None:
        self._items[subscription.subscription_id] = subscription

    def remove(self, sub_id: SubscriptionId) -> bool:
        return self._items.pop(sub_id, None) is not None

    def clear(self) -> None:
        self._items.clear()

    def replace_all(self, subscriptions: Sequence[Subscription]) -> None:
        self._items = {sub.subscription_id: sub for sub in subscriptions}

    def snapshot(self) -> tuple[Subscription, ...]:
        return tuple(self._items.values())

    def list_by_channel(self, channel: AudioChannel) -> tuple[Subscription, ...]:
        return tuple(sub for sub in self._items.values() if sub.channel == channel)

    def list_by_system(self, system: SystemId) -> tuple[Subscription, ...]:
        return tuple(sub for sub in self._items.values() if sub.system == system)

    def list_active(self) -> tuple[Subscription, ...]:
        return tuple(sub for sub in self._items.values() if sub.is_active())

    def list_by_phase(self, phase: SubscriptionPhase) -> tuple[Subscription, ...]:
        return tuple(sub for sub in self._items.values() if sub.state.phase == phase)
