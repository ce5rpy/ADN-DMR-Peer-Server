# ADN DMR Peer Server - application subscription rule timer ops
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

"""Store-native rule_timer_loop; mirrors legacy BRIDGES row semantics."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.routing_table_export import _legacy_to_type
from adn_server.application.routing.helpers import is_special_tg
from adn_server.domain.subscription import Subscription, SubscriptionPhase

logger = logging.getLogger(__name__)


def apply_rule_timer_store(
    store: SubscriptionStore,
    systems_cfg: dict[str, Any],
    now: float,
    *,
    on_relay_deactivated: Callable[[str], None] | None = None,
) -> None:
    """One rule_timer tick: mutate subscriptions in place; prune unused bridge tables."""
    by_table: dict[str, list[Subscription]] = defaultdict(list)
    for sub in store.snapshot():
        by_table[sub.table_key()].append(sub)

    remove_tables: list[str] = []
    debug_msgs: list[str] = []

    for relay_table_key, entries in list(by_table.items()):
        bridge_used = False
        special_tg = is_special_tg(relay_table_key)

        for sub in entries:
            system_name = sub.system.value
            sys_config = systems_cfg.get(system_name, {})
            from adn_server.domain.config_coerce import coerce_bool

            is_single_mode = coerce_bool(sys_config.get("SINGLE_MODE", False))
            to_type = _legacy_to_type(sub)
            active = sub.is_active()
            timer = float(sub.state.timer_expires_at or 0.0)
            is_dynamic = relay_table_key[0:1] != "#" and to_type != "STAT"
            is_obp = sys_config.get("MODE") == "OPENBRIDGE"

            if not is_single_mode and is_dynamic and not is_obp and not special_tg:
                if to_type == "ON":
                    if active:
                        bridge_used = True
                        debug_msgs.append(
                            "(ROUTER) Conference Bridge ACTIVE (INFINITE TIMER): System: %s Bridge: %s, TS: %s, TGID: %s"
                            % (system_name, relay_table_key, sub.channel.slot, int(sub.target_tgid))
                        )
                    else:
                        debug_msgs.append(
                            "(ROUTER) Conference Bridge INACTIVE (no change): System: %s Bridge: %s, TS: %s, TGID: %s"
                            % (system_name, relay_table_key, sub.channel.slot, int(sub.target_tgid))
                        )
                elif to_type == "OFF":
                    if not active:
                        sub.state.phase = SubscriptionPhase.ACTIVE
                        store.upsert(sub)
                        bridge_used = True
                        logger.info(
                            "(ROUTER) Conference Bridge ACTIVATED (NO TIMEOUT): System: %s, Bridge: %s, TS: %s, TGID: %s",
                            system_name,
                            relay_table_key,
                            sub.channel.slot,
                            int(sub.target_tgid),
                        )
                    else:
                        bridge_used = True
                        debug_msgs.append(
                            "(ROUTER) Conference Bridge ACTIVE (no change): System: %s Bridge: %s, TS: %s, TGID: %s"
                            % (system_name, relay_table_key, sub.channel.slot, int(sub.target_tgid))
                        )
            else:
                if to_type == "ON":
                    if active:
                        bridge_used = True
                        if timer < now:
                            sub.state.phase = SubscriptionPhase.IDLE
                            store.upsert(sub)
                            if on_relay_deactivated and relay_table_key[:1] == "#":
                                on_relay_deactivated(system_name)
                            logger.info(
                                "(ROUTER) Conference Bridge TIMEOUT: DEACTIVATE System: %s, Bridge: %s, TS: %s, TGID: %s",
                                system_name,
                                relay_table_key,
                                sub.channel.slot,
                                int(sub.target_tgid),
                            )
                        else:
                            logger.info(
                                "(ROUTER) Conference Bridge ACTIVE (ON timer running): System: %s Bridge: %s, TS: %s, TGID: %s, Timeout in: %.2fs,",
                                system_name,
                                relay_table_key,
                                sub.channel.slot,
                                int(sub.target_tgid),
                                timer - now,
                            )
                    else:
                        debug_msgs.append(
                            "(ROUTER) Conference Bridge INACTIVE (no change): System: %s Bridge: %s, TS: %s, TGID: %s"
                            % (system_name, relay_table_key, sub.channel.slot, int(sub.target_tgid))
                        )
                elif to_type == "OFF":
                    if not active:
                        if timer < now:
                            sub.state.phase = SubscriptionPhase.ACTIVE
                            store.upsert(sub)
                            bridge_used = True
                            logger.info(
                                "(ROUTER) Conference Bridge TIMEOUT: ACTIVATE System: %s, Bridge: %s, TS: %s, TGID: %s",
                                system_name,
                                relay_table_key,
                                sub.channel.slot,
                                int(sub.target_tgid),
                            )
                        else:
                            bridge_used = True
                            logger.info(
                                "(ROUTER) Conference Bridge INACTIVE (OFF timer running): System: %s Bridge: %s, TS: %s, TGID: %s, Timeout in: %.2fs,",
                                system_name,
                                relay_table_key,
                                sub.channel.slot,
                                int(sub.target_tgid),
                                timer - now,
                            )
                    elif active:
                        bridge_used = True
                        debug_msgs.append(
                            "(ROUTER) Conference Bridge ACTIVE (no change): System: %s Bridge: %s, TS: %s, TGID: %s"
                            % (system_name, relay_table_key, sub.channel.slot, int(sub.target_tgid))
                        )
                else:
                    if not is_obp or (is_obp and (to_type == "STAT" or active)):
                        bridge_used = True
                    debug_msgs.append(
                        "(ROUTER) Conference Bridge NO ACTION: System: %s, Bridge: %s, TS: %s, TGID: %s"
                        % (system_name, relay_table_key, sub.channel.slot, int(sub.target_tgid))
                    )

        if not bridge_used:
            remove_tables.append(relay_table_key)

    if debug_msgs:
        logger.debug("\n".join(debug_msgs))

    for key in remove_tables:
        for sub in by_table.get(key, ()):
            store.remove(sub.subscription_id)
        logger.debug("(ROUTER) Unused conference bridge %s removed", key)
