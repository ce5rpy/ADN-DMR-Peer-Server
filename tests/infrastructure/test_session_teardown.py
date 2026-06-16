# ADN DMR Peer Server - tests infrastructure session teardown
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

"""Session teardown executor (legacy reaper wire parity)."""

from __future__ import annotations

from unittest.mock import MagicMock

from adn_server.application.proxy.session_teardown import CLIENT_TEARDOWN_REPEAT, client_teardown_packet, master_teardown_packet
from adn_server.domain.proxy import ClientEndpoint, SessionTeardown
from adn_server.infrastructure.proxy.session_executor import apply_session_teardown
from adn_server.domain.value_objects import bytes_4

_PEER = bytes_4(1234567)
_CLIENT = ClientEndpoint(host="10.0.0.8", port=5000)


def test_apply_session_teardown_sends_rptcl_and_mstcl() -> None:
    master = MagicMock()
    client = MagicMock()
    registry = MagicMock()
    teardown = SessionTeardown(peer_id=_PEER, client=_CLIENT)
    apply_session_teardown(
        teardown,
        master_sink=master,
        client_sender=client,
        peer_registry=registry,
    )
    master.inject.assert_called_once_with(
        master_teardown_packet(_PEER),
        ("10.0.0.8", 5000),
    )
    assert client.send_to_client.call_count == CLIENT_TEARDOWN_REPEAT
    for call in client.send_to_client.call_args_list:
        assert call.args[0] == client_teardown_packet()
        assert call.args[1] == _CLIENT
    registry.remove_peer.assert_called_once_with(_PEER)
