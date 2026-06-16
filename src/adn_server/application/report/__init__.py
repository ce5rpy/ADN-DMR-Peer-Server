# ADN DMR Peer Server - application report   init  
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

"""Report application layer: payload mapping and protocol mode (no Twisted / wire bytes)."""

from .queue import (
    DEFAULT_MAX_DRAIN_PER_TICK,
    DEFAULT_MAX_EVENTS,
    BoundedReportQueue,
    QueuedReportSender,
)
from .dashboard_state import build_dashboard_state
from .payloads import (
    REPORT_FEATURES,
    REPORT_PROTOCOL,
    build_routing_table,
    build_topology,
    hello_connected_system_names,
    parse_bridge_event_csv,
    routing_table_delta,
    topology_delta,
)

__all__ = [
    "DEFAULT_MAX_DRAIN_PER_TICK",
    "DEFAULT_MAX_EVENTS",
    "BoundedReportQueue",
    "QueuedReportSender",
    "REPORT_FEATURES",
    "REPORT_PROTOCOL",
    "build_dashboard_state",
    "build_routing_table",
    "build_topology",
    "hello_connected_system_names",
    "parse_bridge_event_csv",
    "routing_table_delta",
    "topology_delta",
]
