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
