# ADN DMR Peer Server - application subscription subscription debug ops
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

"""Store-native subscription_debug_loop."""

from __future__ import annotations

import logging
from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.routing_table_export import _legacy_to_type
from adn_server.domain import bytes_3
from adn_server.domain.subscription import (
    ActivationPolicy,
    AudioChannel,
    InbandTriggers,
    Subscription,
    SubscriptionPhase,
    SubscriptionRole,
    SubscriptionState,
    SystemId,
    TgId,
)

logger = logging.getLogger(__name__)

_PROHIBITED_TABLE_KEYS = tuple(str(b) for b in range(10)) + tuple(f"#{b}" for b in range(10))


def apply_subscription_debug_store(
    store: SubscriptionStore,
    systems_cfg: dict[str, Any],
    now: float,
) -> None:
    """Remove invalid bridge keys and fix >1 active dial (#) bridge per MASTER."""
    for key in _PROHIBITED_TABLE_KEYS:
        for sub in [s for s in store.snapshot() if s.table_key() == key]:
            store.remove(sub.subscription_id)

    statroll = sum(1 for sub in store.snapshot() if _legacy_to_type(sub) == "STAT")

    for system, sys_cfg in systems_cfg.items():
        bridgeroll = 0
        dialroll = 0
        activeroll = 0
        for sub in store.snapshot():
            if sub.system.value != system:
                continue
            bridgeroll += 1
            if sub.is_active():
                if sub.table_key().startswith("#"):
                    dialroll += 1
                    activeroll += 1
                else:
                    activeroll += 1
        if bridgeroll:
            logger.debug(
                "(BRIDGEDEBUG) system %s has %s bridges of which %s are in an ACTIVE state",
                system,
                bridgeroll,
                activeroll,
            )
        if dialroll > 1 and sys_cfg.get("MODE") == "MASTER":
            logger.warning(
                "(BRIDGEDEBUG) system %s has more than one active dial bridge (%s) - fixing",
                system,
                dialroll,
            )
            _fix_duplicate_dial_bridges(store, system, sys_cfg, now)

    logger.info("(BRIDGEDEBUG) The server currently has %s STATic bridges", statroll)


def _fix_duplicate_dial_bridges(
    store: SubscriptionStore,
    system: str,
    sys_cfg: dict[str, Any],
    now: float,
) -> None:
    times: dict[float, str] = {}
    for sub in store.snapshot():
        if sub.system.value != system or not sub.is_active():
            continue
        relay_table_key = sub.table_key()
        if not relay_table_key.startswith("#"):
            continue
        timer = sub.state.timer_expires_at
        if isinstance(timer, (int, float)):
            times[float(timer)] = relay_table_key

    _tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
    timeout_sec = _tmout * 60.0
    system_id = SystemId(system)

    for relay_table_key in set(times.values()):
        logger.warning("(BRIDGEDEBUG) deactivating system: %s for bridge: %s", system, relay_table_key)
        try:
            setbridge = int(relay_table_key[1:]) if relay_table_key.startswith("#") else int(relay_table_key)
        except ValueError:
            setbridge = 9
        on_trigger = bytes_3(setbridge)

        for sub in list(store.snapshot()):
            if sub.system != system_id or sub.table_key() != relay_table_key:
                continue
            if int(sub.channel.slot) != 2:
                continue
            store.remove(sub.subscription_id)
            store.upsert(
                Subscription(
                    channel=AudioChannel(tgid=TgId(9), slot=2),
                    system=system_id,
                    target_tgid=TgId(9),
                    role=SubscriptionRole.SINK,
                    policy=ActivationPolicy.INBAND,
                    state=SubscriptionState(
                        phase=SubscriptionPhase.IDLE,
                        timer_expires_at=now + timeout_sec,
                    ),
                    relay_table_key=relay_table_key,
                    timeout_seconds=timeout_sec,
                    triggers=InbandTriggers(on=(on_trigger,), off=(), reset=()),
                )
            )
