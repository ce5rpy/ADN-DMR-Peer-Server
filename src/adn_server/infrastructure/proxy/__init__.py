# ADN DMR Peer Server - infrastructure proxy   init
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

"""Proxy infrastructure adapters (Phase 3)."""

from .config import apply_proxy_env_overrides, proxy_settings
from .hbp_adapters import FanInClientSender, HbpMasterPeerRegistry, InProcessHbpSink
from .ip_blacklist import InMemoryProxyIpBlacklist
from .reply_transport import ProxyReplyTransport
from .rpto_queue import InMemoryPendingRptoQueue
from .runtime import ProxyServiceState, apply_proxy_config_reload, start_proxy_service
from .self_service_config import self_service_settings
from .session_executor import apply_session_teardown
from .slot_store import InMemoryProxySlotStore
from .udp_fanin import ProxyFanInProtocol, listen_proxy_fanin

__all__ = [
    "FanInClientSender",
    "HbpMasterPeerRegistry",
    "InMemoryPendingRptoQueue",
    "InMemoryProxyIpBlacklist",
    "InMemoryProxySlotStore",
    "InProcessHbpSink",
    "ProxyFanInProtocol",
    "ProxyReplyTransport",
    "ProxyServiceState",
    "apply_proxy_config_reload",
    "apply_proxy_env_overrides",
    "apply_session_teardown",
    "listen_proxy_fanin",
    "proxy_settings",
    "self_service_settings",
    "start_proxy_service",
]
