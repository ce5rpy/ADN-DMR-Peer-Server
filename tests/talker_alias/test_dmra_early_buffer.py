"""DMRA may arrive before DMRD VHEAD — legacy buffers under rf_src until stream note."""

from __future__ import annotations

from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.talker_alias import build_dmra_packet, decode_ta_from_blocks
from adn_server.infrastructure.hbp_constants import DMRA

from tests.support.hbp_repeat_stack import build_hbp_repeat_stack
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.talker_alias.test_mmdvm_wire import mmdvm_wire_blocks


_PEER_TX = bytes_4(730039210)
_PEER_RX = bytes_4(730039101)
_ADDR_TX = ("10.0.0.1", 62001)
_ADDR_RX = ("10.0.0.2", 62002)


def test_dmra_before_vhead_passthrough_on_repeat() -> None:
    """Regression: early DMRA was dropped when stream_id mapping did not exist yet."""
    stack = build_hbp_repeat_stack(talker_alias=True)
    stack.config["GLOBAL"]["TALKER_ALIAS_MODE"] = "passthrough"
    stack.register_peer(_PEER_TX, _ADDR_TX)
    stack.register_peer(_PEER_RX, _ADDR_RX)

    rf_src = bytes_3(3120001)
    text = "CE5RPY Radio"
    for block_id, payload in mmdvm_wire_blocks(text).items():
        stack.inject(build_dmra_packet(rf_src, block_id, payload), _ADDR_TX)

    base = PacketSpec(peer_id=730039210, rf_src=3120001, dst_id=7304, slot=2, stream_id=0xA1B2C3D4)
    stack.inject_spec(DeterministicScenario.voice_head_spec(base), _ADDR_TX)

    assert stack.dmra_capture, "passthrough DMRA should be sent on VHEAD"
    packets, exclude = stack.dmra_capture[0]
    assert exclude == _PEER_TX
    assert all(p[:4] == DMRA for p in packets)
    rebuilt = {i: packets[i][8:15] for i in range(len(packets))}
    assert decode_ta_from_blocks(rebuilt) == text

    dmra_to_rx = [p for p, _ in stack.transport.sent if p[:4] == DMRA and _ == _ADDR_RX]
    assert dmra_to_rx, "listening peer should receive passthrough DMRA"


def test_promote_provisional_dmra_buffer() -> None:
    stack = build_hbp_repeat_stack(talker_alias=True)
    hbp = stack.hbp
    peer = _PEER_TX
    rf_src = bytes_3(3120001)
    stream_id = bytes_4(0x12345678)
    blocks = mmdvm_wire_blocks("TA early")

    for block_id, payload in blocks.items():
        hbp.store_dmra_packet(peer, build_dmra_packet(rf_src, block_id, payload))

    assert hbp.get_dmra_blocks(rf_src) is not None
    assert hbp.get_dmra_blocks(stream_id) is None

    hbp.note_dmrd_stream(peer, rf_src, stream_id)

    promoted = hbp.get_dmra_blocks(stream_id)
    assert promoted is not None
    assert decode_ta_from_blocks(promoted) == "TA early"
    assert hbp.get_dmra_blocks(rf_src) is None
