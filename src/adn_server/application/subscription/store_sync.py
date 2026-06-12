# ADN DMR Peer Server - application subscription store sync
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
