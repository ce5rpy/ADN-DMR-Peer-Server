# ADN DMR Peer Server - tests talker alias mmdvm wire
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

"""MMDVMHost DMRA wire layout and short TA passthrough."""

from __future__ import annotations

from bitarray import bitarray

from adn_server.application.talker_alias_use_cases import passthrough_complete, passthrough_packets_from_blocks
from adn_server.domain.talker_alias import (
    decode_ta_from_blocks,
    encode_utf8,
    parse_dmra_packet,
    required_ta_block_count,
    store_ta_from_embed_lc,
    talker_alias_block_id_from_lc,
    talker_alias_lc_bytes,
    try_buffer_ta_from_voice_fragments,
)
from adn_server.domain.dmr.bptc import encode_emblc
from adn_server.infrastructure.talker_alias_emblc import encode_talker_alias_emblc

_encode_emblc_correct = encode_emblc


def _voice_pkt_with_embed(frag: bitarray) -> bytes:
    dmrbits = bitarray(264, endian="big")
    dmrbits.setall(0)
    dmrbits[116:148] = frag
    return dmrbits.tobytes()[:33]
def mmdvm_wire_blocks(text: str) -> dict[int, bytes]:
    """Build wire payloads as MMDVMHost writeTalkerAlias / CDMRTA::add (m_buf[block*7:])."""
    buf = encode_utf8(text)
    count = required_ta_block_count(buf)
    blocks: dict[int, bytes] = {}
    for block_id in range(count):
        start = block_id * 7
        blocks[block_id] = buf[start : start + 7]
    return blocks


def test_passthrough_complete_single_mmdvm_wire_block_ce5rpy() -> None:
    blocks = mmdvm_wire_blocks("CE5RPY")
    assert passthrough_complete(blocks) is True
    assert decode_ta_from_blocks(blocks) == "CE5RPY"


def test_passthrough_complete_mmdvm_wire_two_blocks() -> None:
    blocks = mmdvm_wire_blocks("CE5RPY Rodrigo")
    assert passthrough_complete(blocks) is True
    assert decode_ta_from_blocks(blocks) == "CE5RPY Rodrigo"


def test_peer_dmra_non_mmdvm_layout_rejected() -> None:
    """Pi-Star log with byte7=0x3D is not MMDVM writeTalkerAlias (type must be 0-3)."""
    data = b"DMRA+\x83\x83=oe(\x00\x8cCE"
    assert parse_dmra_packet(data) is None


def test_talker_alias_block_id_from_lc() -> None:
    lc9 = talker_alias_lc_bytes(2, encode_utf8("CE5RPY")[0:7])
    assert talker_alias_block_id_from_lc(lc9) == 2
    assert talker_alias_block_id_from_lc(b"\x00\x00" + b"\x00" * 7) is None


def test_buffer_ta_from_voice_fragments_decodes_ce5rpy() -> None:
    """Voice bursts B–E carrying a correctly FEC-encoded TA decode losslessly to CE5RPY."""
    text = "CE5RPY"
    lc9 = talker_alias_lc_bytes(0, encode_utf8(text)[0:7])
    frags = _encode_emblc_correct(lc9)
    blocks: dict[int, bytes] = {}
    acc: dict[int, object] = {}
    for vseq in (1, 2, 3):
        assert not try_buffer_ta_from_voice_fragments(acc, vseq, _voice_pkt_with_embed(frags[vseq]), blocks)
    assert try_buffer_ta_from_voice_fragments(acc, 4, _voice_pkt_with_embed(frags[4]), blocks)
    assert passthrough_complete(blocks)
    assert decode_ta_from_blocks(blocks) == text


def test_injected_emblc_round_trips_losslessly() -> None:
    """Injected embedded LC must survive decode_emblc (regression: 'Rodrigo' -> 'Rodrigg').

    The upstream dmr_utils3 encoder corrupted segment D (bit 25); our vendored encoder fixes it,
    so every injected block round-trips through decode_emblc.
    """
    from adn_server.domain.dmr import bptc

    text = "CE5RPY Rodrigo"
    emblcs, count = encode_talker_alias_emblc(text)
    assert count >= 3
    recovered: dict[int, bytes] = {}
    for block_id, emblc in enumerate(emblcs):
        lc = bptc.decode_emblc(emblc[1] + emblc[2] + emblc[3] + emblc[4])
        assert lc == talker_alias_lc_bytes(block_id, encode_utf8(text)[block_id * 7 : block_id * 7 + 7])
        recovered[block_id] = lc[2:9]
    assert decode_ta_from_blocks(recovered) == text


def test_buffer_ta_from_voice_ignores_group_lc() -> None:
    """Group-call embedded LC (FLCO 0) is not stored as TA."""
    group_lc = bytes([0x00, 0x00]) + b"\x00\x12\x34\x00\x00\x07\x53"
    frags = _encode_emblc_correct(group_lc)
    blocks: dict[int, bytes] = {}
    acc: dict[int, object] = {}
    for vseq in (1, 2, 3, 4):
        try_buffer_ta_from_voice_fragments(acc, vseq, _voice_pkt_with_embed(frags[vseq]), blocks)
    assert blocks == {}


def test_store_ta_from_embed_lc_matches_wire() -> None:
    """Wire payload == lc9[2:9] per DMRNetwork::writeTalkerAlias."""
    text = "CE5RPY"
    encoded = encode_utf8(text)
    lc9 = talker_alias_lc_bytes(0, encoded[0:7])
    blocks: dict[int, bytes] = {}
    assert store_ta_from_embed_lc(blocks, 0, lc9)
    parsed = parse_dmra_packet(b"DMRA" + b"\x00\x00\x01" + bytes([0]) + blocks[0])
    assert parsed is not None
    assert parsed[2] == blocks[0]


def test_mmdvm_three_byte_id_layout() -> None:
    data = b"DMRA\x2b\x83\x83\x01" + b"\x00" * 7
    parsed = parse_dmra_packet(data)
    assert parsed == (bytes([0x2B, 0x83, 0x83]), 1, b"\x00" * 7)


def test_passthrough_packets_sends_only_required_blocks() -> None:
    from tests.talker_alias.test_passthrough import _complete_blocks

    rf = bytes([0x2B, 0x83, 0x83])
    blocks = _complete_blocks("CE5RPY")
    packets = passthrough_packets_from_blocks(rf, blocks)
    assert len(packets) == 1
    assert packets[0][7] == 0
