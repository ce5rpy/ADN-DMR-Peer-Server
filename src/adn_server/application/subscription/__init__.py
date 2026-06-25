# ADN DMR Peer Server - application subscription   init
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

"""Subscription application helpers."""

from .ingress import build_voice_ingress
from .router import SubscriptionRouter
from .routing_table_export import export_routing_table, subscription_to_legacy_row
from .routing_table_import import subscriptions_from_routing_table
from .routing_table_legacy_view import RoutingTableLegacyView
from .store_sync import replace_store_from_routing_table
from .subscription_queries import (
    active_system_slots_for_tg_in_store,
    store_has_table,
    system_has_active_leg_in_store,
)

__all__ = [
    "RoutingTableLegacyView",
    "SubscriptionRouter",
    "active_system_slots_for_tg_in_store",
    "build_voice_ingress",
    "export_routing_table",
    "replace_store_from_routing_table",
    "store_has_table",
    "subscription_to_legacy_row",
    "subscriptions_from_routing_table",
    "system_has_active_leg_in_store",
]
