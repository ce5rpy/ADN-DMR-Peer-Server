"""Live UDP smoke test for integrated proxy (isolated port; no production restart)."""

from __future__ import annotations

import socket
import threading

import pytest
from twisted.internet import reactor

from adn_server.application.proxy import ProxyUseCases
from adn_server.domain.value_objects import bytes_4
from adn_server.infrastructure.config_normalizer import ensure_system_runtime_config
from adn_server.infrastructure.hbp_constants import RPTACK, RPTL
from adn_server.infrastructure.proxy import (
    InMemoryPendingRptoQueue,
    InMemoryProxySlotStore,
    InProcessHbpSink,
    ProxyFanInProtocol,
    ProxyReplyTransport,
)
from adn_server.infrastructure.twisted_adapters.udp_hbp import HBPProtocol

_SMOKE_PORT = 62032
_PEER = bytes_4(1234567)


class _AclRouter:
    def acl_check(self, peer_id: bytes, acl: object) -> bool:
        return True


def _build_fanin() -> ProxyFanInProtocol:
    config = {
        "GLOBAL": {"PING_TIME": 10, "MAX_MISSED": 3, "USE_ACL": False},
        "SYSTEMS": {
            "HOTSPOT": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 8,
                "OPTIONS": "TS2=9990;",
            }
        },
    }
    ensure_system_runtime_config(config)
    hbp = HBPProtocol("HOTSPOT", config)
    hbp._router = _AclRouter()  # type: ignore[assignment]
    proxy = ProxyUseCases(
        InMemoryProxySlotStore(),
        InMemoryPendingRptoQueue(),
        max_peers=8,
    )
    sink = InProcessHbpSink(hbp)
    fanin = ProxyFanInProtocol(proxy, sink)
    return fanin, hbp, sink


@pytest.mark.smoke
def test_live_udp_rptl_rptack_on_isolated_port() -> None:
    """RPTL in → inject → RPTACK out on 127.0.0.1:62032 (does not use production 62031)."""
    fanin, hbp, _ = _build_fanin()
    result: dict[str, bytes | None] = {"reply": None, "error": None}

    def _run_client() -> None:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client.settimeout(2.0)
            client.bind(("127.0.0.1", 0))
            client.sendto(RPTL + _PEER, ("127.0.0.1", _SMOKE_PORT))
            data, _ = client.recvfrom(4096)
            result["reply"] = data
            client.close()
        except OSError as exc:
            result["error"] = str(exc).encode()
        finally:
            reactor.callFromThread(reactor.stop)

    listener = reactor.listenUDP(_SMOKE_PORT, fanin, interface="127.0.0.1")
    hbp.transport = ProxyReplyTransport(fanin.transport)
    reactor.callWhenRunning(
        lambda: threading.Thread(target=_run_client, daemon=True).start()
    )
    reactor.callLater(5.0, reactor.stop)
    reactor.run()

    listener.stopListening()
    if result["error"]:
        pytest.fail(result["error"].decode())
    reply = result["reply"]
    assert reply is not None, "no UDP reply (timeout?)"
    assert reply.startswith(RPTACK), f"expected RPTACK, got {reply[:8]!r}"
