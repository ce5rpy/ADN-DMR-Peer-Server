# ADN DMR Peer Server - application routing dynamic tg restore
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

"""Bridge/subscription sync after dynamic TG rows are restored from persistence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.routing_table_export import _legacy_to_type
from adn_server.application.subscription.subscription_queries import store_has_table
from adn_server.domain import bytes_3
from adn_server.domain.dynamic_tg import DynamicTgEntry
from adn_server.domain.subscription import SubscriptionPhase


def sync_restored_dynamic_bridges(
    entries: list[DynamicTgEntry],
    *,
    system_name: str,
    peer_id: bytes,
    sys_cfg: dict[str, Any],
    sub_store: SubscriptionStore,
    ensure_dynamic_relay: Callable[[bytes, str, int, float], None],
    ua_timer_minutes_for_peer: Callable[[str, bytes], float] | None,
    now: float,
) -> None:
    """Align bridge timers and create missing relay tables for restored dynamics."""
    for entry in entries:
        if not entry.single_mode or entry.expires_at is None:
            continue
        exp = float(entry.expires_at)
        if exp <= now:
            continue
        for sub in sub_store.snapshot():
            if (
                sub.table_key() == str(entry.tgid)
                and sub.system.value == system_name
                and int(sub.channel.slot) == int(entry.slot)
            ):
                sub.state.timer_expires_at = exp
                if not sub.is_active() and _legacy_to_type(sub) == "ON":
                    sub.state.phase = SubscriptionPhase.ACTIVE
                sub_store.upsert(sub)
    tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
    if ua_timer_minutes_for_peer is not None:
        tmout = float(ua_timer_minutes_for_peer(system_name, peer_id))
    seen: set[tuple[int, int]] = set()
    for entry in entries:
        key = (int(entry.tgid), int(entry.slot))
        if key in seen or store_has_table(sub_store, str(entry.tgid)):
            continue
        seen.add(key)
        ensure_dynamic_relay(bytes_3(entry.tgid), system_name, int(entry.slot), tmout)
