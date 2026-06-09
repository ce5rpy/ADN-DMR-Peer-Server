"""Proxy fan-in → MASTER inject → REPEAT to second hotspot (DroidStar path)."""

from __future__ import annotations

import pytest
from bitarray import bitarray

from adn_server.application.proxy import ProxyUseCases
from adn_server.domain import bytes_4
from adn_server.infrastructure.config_normalizer import ensure_system_runtime_config
from adn_server.infrastructure.hbp_constants import DMRD
from adn_server.infrastructure.proxy import (
    InMemoryPendingRptoQueue,
    InMemoryProxySlotStore,
    InProcessHbpSink,
    ProxyFanInProtocol,
    ProxyReplyTransport,
)
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.support.hbp_repeat_stack import HbpRepeatStack, build_hbp_repeat_stack

pytestmark = pytest.mark.integration

_PEER_TX = bytes_4(730039210)
_PEER_RX = bytes_4(730039101)
_ADDR_TX = ("192.168.50.10", 62031)
_ADDR_RX = ("192.168.50.20", 62032)
_EMB_SLICE = slice(116, 148)


def _proxy_fanin_stack() -> tuple[ProxyFanInProtocol, HbpRepeatStack]:
    stack = build_hbp_repeat_stack(talker_alias=True, system_name="MASTER-A")
    stack.register_peer(_PEER_TX, _ADDR_TX)
    stack.register_peer(_PEER_RX, _ADDR_RX)

    proxy = ProxyUseCases(
        InMemoryProxySlotStore(),
        InMemoryPendingRptoQueue(),
        max_peers=8,
    )
    sink = InProcessHbpSink(stack.hbp)
    fanin = ProxyFanInProtocol(proxy, sink)
    fanin.transport = stack.transport  # type: ignore[assignment]
    stack.hbp.transport = ProxyReplyTransport(stack.transport)
    return fanin, stack


def test_proxy_inject_repeat_reaches_listener_with_embed_lc() -> None:
    """TX via proxy (DroidStar) must REPEAT to other peer with TA embed, not raw copy."""
    fanin, stack = _proxy_fanin_stack()
    base = PacketSpec(
        peer_id=730039210,
        rf_src=7300392,
        dst_id=7304,
        slot=2,
        stream_id=0x11223344,
        payload=b"\x00" * 33,
    )
    vhead = DeterministicScenario.voice_head_spec(base)
    burst = DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1)

    fanin.datagramReceived(vhead.data(), _ADDR_TX)
    stack.transport.clear()
    fanin.datagramReceived(burst.data(), _ADDR_TX)

    listener_pkts = [p for p in stack.transport.for_addr(_ADDR_RX) if p[:4] == DMRD]
    assert len(listener_pkts) == 1
    bits = bitarray(endian="big")
    bits.frombytes(listener_pkts[0][20:53])
    slot_st = stack.hbp.STATUS[2]
    assert slot_st.get("TX_TA_EMB") is not None
    assert bits[_EMB_SLICE] == slot_st["REP_EMB_LC"][1]
    assert listener_pkts[0][20:53] != burst.payload


def test_proxy_attach_binds_sockaddr_used_for_master_ingress() -> None:
    """Peer must be registered at proxy client addr so DMRD is accepted and REPEAT fans out."""
    fanin, stack = _proxy_fanin_stack()
    ensure_system_runtime_config(stack.config)
    packet = DeterministicScenario.voice_head_spec(
        PacketSpec(peer_id=730039210, stream_id=0x55667788)
    ).data()

    fanin.datagramReceived(packet, _ADDR_TX)
    assert stack.hbp._peers[_PEER_TX]["SOCKADDR"] == _ADDR_TX
    rx_traffic = stack.transport.for_addr(_ADDR_RX)
    assert rx_traffic, "REPEAT must reach the other logged-in hotspot"
    assert any(p[:4] == DMRD for p in rx_traffic)
