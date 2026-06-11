"""Read-only queries on ``SubscriptionStore`` (runtime routing authority)."""

from __future__ import annotations

from adn_server.application.ports import SubscriptionStore
from adn_server.domain.subscription import Subscription


def store_has_table(store: SubscriptionStore, table_key: str) -> bool:
    """True when the store has at least one leg in ``table_key``."""
    return any(sub.table_key() == table_key for sub in store.snapshot())


def system_has_active_leg_in_store(
    store: SubscriptionStore,
    system: str,
    slot: int,
    tgid: int,
) -> bool:
    """True when an ACTIVE subscription leg exists for ``(system, slot, tgid)``."""
    indexed = getattr(store, "has_active_target_leg", None)
    if callable(indexed):
        return bool(indexed(system, slot, tgid))
    for sub in store.snapshot():
        if sub.system.value != system:
            continue
        if int(sub.channel.slot) != int(slot):
            continue
        if int(sub.target_tgid) != int(tgid):
            continue
        if sub.is_active():
            return True
    return False


def active_system_slots_for_tg_in_store(
    store: SubscriptionStore,
    system: str,
    tgid: int,
) -> tuple[int, ...]:
    """Return sorted unique slots with an ACTIVE leg for ``system`` on bridge table ``tgid``."""
    slots: list[int] = []
    table_key = str(tgid)
    for sub in store.snapshot():
        if sub.table_key() != table_key:
            continue
        if sub.system.value != system:
            continue
        if not sub.is_active():
            continue
        slot = int(sub.channel.slot)
        if slot not in slots:
            slots.append(slot)
    return tuple(sorted(slots))


def store_legs_for_table(
    store: SubscriptionStore,
    table_key: str,
) -> tuple[Subscription, ...]:
    """All subscription legs in a bridge table."""
    return tuple(sub for sub in store.snapshot() if sub.table_key() == table_key)
