# ADN DMR Peer Server - application subscription subscription queries
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


def system_has_other_active_bridge_on_slot(
    store: SubscriptionStore,
    system: str,
    slot: int,
    incoming_tgid: int,
) -> bool:
    """True when another ACTIVE bridge leg occupies ``(system, slot)`` on a different TG.

    Diagnostic / table export only — static OPTIONS bridges stay ACTIVE idle and must
    not gate per-peer downlink (see ``peer_voice_slots`` / hangtime in ``downlink.py``).
    """
    incoming = int(incoming_tgid)
    for sub in store.snapshot():
        if sub.system.value != system:
            continue
        if int(sub.channel.slot) != int(slot):
            continue
        if not sub.is_active():
            continue
        if int(sub.target_tgid) != incoming:
            return True
    return False


def bridge_timer_active_on_slot(
    store: SubscriptionStore,
    system: str,
    slot: int,
    tgid: int,
    *,
    now: float,
) -> bool:
    """True when an ACTIVE bridge leg for ``tgid`` on ``slot`` still has a live timer."""
    tg = int(tgid)
    for sub in store.snapshot():
        if sub.system.value != system:
            continue
        if int(sub.channel.slot) != int(slot):
            continue
        if int(sub.target_tgid) != tg:
            continue
        if not sub.is_active():
            continue
        exp = sub.state.timer_expires_at
        if exp is not None and float(exp) > float(now):
            return True
    return False


def store_legs_for_table(
    store: SubscriptionStore,
    table_key: str,
) -> tuple[Subscription, ...]:
    """All subscription legs in a bridge table."""
    return tuple(sub for sub in store.snapshot() if sub.table_key() == table_key)
