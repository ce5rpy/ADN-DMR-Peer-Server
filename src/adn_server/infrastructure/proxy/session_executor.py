# ADN DMR Peer Server - infrastructure proxy session executor
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

"""Execute proxy session teardown via application ports (infrastructure)."""

from __future__ import annotations

from adn_server.application.ports import MasterPeerRegistry, ProxyClientSender, ProxyMasterSink
from adn_server.application.proxy.session_teardown import (
    CLIENT_TEARDOWN_REPEAT,
    client_teardown_packet,
    master_teardown_packet,
)
from adn_server.domain.proxy import SessionTeardown


def apply_session_teardown(
    teardown: SessionTeardown,
    *,
    master_sink: ProxyMasterSink,
    client_sender: ProxyClientSender,
    peer_registry: MasterPeerRegistry,
) -> None:
    """Legacy reaper: RPTCL inject, MSTCL×3 to client, drop MASTER peer."""
    client_addr = (teardown.client.host, teardown.client.port)
    master_sink.inject(master_teardown_packet(teardown.peer_id), client_addr)
    pkt = client_teardown_packet()
    for _ in range(CLIENT_TEARDOWN_REPEAT):
        client_sender.send_to_client(pkt, teardown.client)
    peer_registry.remove_peer(teardown.peer_id)
