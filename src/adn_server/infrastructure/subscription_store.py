"""In-memory subscription store (Phase 2 runtime routing authority)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from adn_server.application.ports import SubscriptionStore
from adn_server.domain.subscription import (
    AudioChannel,
    Subscription,
    SubscriptionId,
    SubscriptionPhase,
    SystemId,
)

_IndexKey = tuple[str, int, int]


class InMemorySubscriptionStore(SubscriptionStore):
    """Hold subscriptions keyed by ``SubscriptionId``; maintains hot-path indexes."""

    def __init__(self) -> None:
        self._items: dict[SubscriptionId, Subscription] = {}
        self._by_table: dict[str, list[Subscription]] = defaultdict(list)
        self._source_tables: dict[_IndexKey, set[str]] = {}
        self._active_target_counts: dict[_IndexKey, int] = {}

    def get(self, sub_id: SubscriptionId) -> Subscription | None:
        return self._items.get(sub_id)

    def upsert(self, subscription: Subscription) -> None:
        old = self._items.get(subscription.subscription_id)
        if old is not None:
            self._unindex(old)
        self._items[subscription.subscription_id] = subscription
        self._index(subscription)

    def remove(self, sub_id: SubscriptionId) -> bool:
        old = self._items.pop(sub_id, None)
        if old is None:
            return False
        self._unindex(old)
        return True

    def clear(self) -> None:
        self._items.clear()
        self._by_table.clear()
        self._source_tables.clear()
        self._active_target_counts.clear()

    def replace_all(self, subscriptions: Sequence[Subscription]) -> None:
        self.clear()
        for sub in subscriptions:
            self._items[sub.subscription_id] = sub
            self._index(sub)

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

    def relay_tables_with_active_source(
        self,
        system: str,
        slot: int,
        dst_tgid: int,
    ) -> tuple[str, ...]:
        """O(1) lookup: table keys with an ACTIVE source on (system, slot, dst_tgid)."""
        keys = self._source_tables.get((system, int(slot), int(dst_tgid)))
        if not keys:
            return ()
        return tuple(sorted(keys))

    def legs_in_table(self, table_key: str) -> tuple[Subscription, ...]:
        """All legs for a relay table key (indexed)."""
        return tuple(self._by_table.get(table_key, ()))

    def has_active_target_leg(self, system: str, slot: int, tgid: int) -> bool:
        """True when any ACTIVE leg exists for ``(system, slot, target_tgid)``."""
        return self._active_target_counts.get((system, int(slot), int(tgid)), 0) > 0

    def _index_key(self, sub: Subscription) -> _IndexKey:
        return (sub.system.value, int(sub.channel.slot), int(sub.target_tgid))

    def _index(self, sub: Subscription) -> None:
        table_key = sub.table_key()
        self._by_table[table_key].append(sub)
        if sub.is_active():
            key = self._index_key(sub)
            self._source_tables.setdefault(key, set()).add(table_key)
            self._active_target_counts[key] = self._active_target_counts.get(key, 0) + 1

    def _unindex(self, sub: Subscription) -> None:
        table_key = sub.table_key()
        legs = self._by_table.get(table_key)
        if legs:
            try:
                legs.remove(sub)
            except ValueError:
                pass
            if not legs:
                del self._by_table[table_key]
        if sub.is_active():
            key = self._index_key(sub)
            keys = self._source_tables.get(key)
            if keys is not None:
                keys.discard(table_key)
                if not keys:
                    del self._source_tables[key]
            count = self._active_target_counts.get(key, 0) - 1
            if count <= 0:
                self._active_target_counts.pop(key, None)
            else:
                self._active_target_counts[key] = count
