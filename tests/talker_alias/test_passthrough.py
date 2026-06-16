# ADN DMR Peer Server - tests talker alias passthrough
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

"""Talker Alias passthrough and both modes."""

from __future__ import annotations

from tests.harness.scenarios import make_talker_alias_use_cases, talker_alias_config

from adn_server.application.talker_alias_use_cases import (
    passthrough_complete,
    passthrough_packets_from_blocks,
)
from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.talker_alias import (
    DMRA_BLOCK_COUNT,
    DMRA_OPCODE,
    blocks_from_buffer,
    buffer_from_blocks,
    decode_7bit,
    encode_utf8,
)


def _complete_blocks(text: str) -> dict[int, bytes]:
    payloads = blocks_from_buffer(encode_utf8(text))
    return {i: payloads[i] for i in range(DMRA_BLOCK_COUNT)}


def _passthrough_config() -> dict:
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "passthrough"
    return config


def test_passthrough_complete_full_adn_blocks() -> None:
    blocks = _complete_blocks("CE5RPY Test")
    assert passthrough_complete(blocks) is True


def test_passthrough_complete_partial_adn_blocks_fails() -> None:
    blocks = _complete_blocks("CE5RPY Test")
    assert passthrough_complete({0: blocks[0]}) is False


def test_passthrough_packets_rebuild_dmra_opcode() -> None:
    text = "CE5RPY Test"
    blocks = _complete_blocks(text)
    rf_src = bytes_3(3120001)
    packets = passthrough_packets_from_blocks(rf_src, blocks)

    assert 1 <= len(packets) <= DMRA_BLOCK_COUNT
    assert all(p[:4] == DMRA_OPCODE for p in packets)
    assert all(p[4:7] == rf_src for p in packets)
    rebuilt = {i: packets[i][8:15] for i in range(len(packets))}
    assert decode_7bit(buffer_from_blocks(rebuilt)) == text


def test_packets_for_stream_passthrough_mode() -> None:
    config = _passthrough_config()
    ta = make_talker_alias_use_cases(config)
    stream_id = bytes_4(0xA1A1A1A1)
    blocks = _complete_blocks("CE5RPY Rodrigo")

    def get_blocks(_system: str, _stream: bytes) -> dict[int, bytes]:
        return blocks

    packets = ta.packets_for_stream(
        "MASTER-A",
        bytes_3(3120001),
        stream_id,
        get_blocks,
        target_system="MASTER-B",
    )

    assert packets is not None
    assert 1 <= len(packets) <= DMRA_BLOCK_COUNT
    assert all(p[:4] == DMRA_OPCODE for p in packets)


def test_packets_for_stream_passthrough_without_blocks_returns_none() -> None:
    config = _passthrough_config()
    ta = make_talker_alias_use_cases(config)

    assert (
        ta.packets_for_stream(
            "MASTER-A",
            bytes_3(3120001),
            bytes_4(0xB2B2B2B2),
            lambda _s, _st: None,
            target_system="MASTER-B",
        )
        is None
    )


def test_packets_for_stream_both_prefers_passthrough() -> None:
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "both"
    ta = make_talker_alias_use_cases(config)
    passthrough_text = "From radio"
    blocks = _complete_blocks(passthrough_text)

    packets = ta.packets_for_stream(
        "MASTER-A",
        bytes_3(9999999),
        bytes_4(0xC3C3C3C3),
        lambda _s, _st: blocks,
        target_system="MASTER-B",
    )

    assert packets is not None
    expected = passthrough_packets_from_blocks(bytes_3(9999999), blocks)
    assert packets == expected


def test_packets_for_stream_both_without_blocks_injects_like_legacy() -> None:
    """both + empty buffer at VHEAD: legacy resolve_ta injects the template immediately."""
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "both"
    ta = make_talker_alias_use_cases(config)

    packets = ta.packets_for_stream(
        "MASTER-A",
        bytes_3(3120001),
        bytes_4(0xD4D4D4D4),
        lambda _s, _st: None,
        target_system="MASTER-B",
    )
    assert packets is not None
    assert all(p[:4] == DMRA_OPCODE for p in packets)


def test_packets_for_stream_both_fallback_inject_when_no_source_ta() -> None:
    """both + window elapsed with no source TA: fall back to injecting the template."""
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "both"
    ta = make_talker_alias_use_cases(config)

    packets = ta.packets_for_stream(
        "MASTER-A",
        bytes_3(3120001),
        bytes_4(0xE5E5E5E5),
        lambda _s, _st: None,
        target_system="MASTER-B",
        fallback_inject=True,
    )

    assert packets is not None
    assert 1 <= len(packets) <= DMRA_BLOCK_COUNT
    assert all(p[:4] == DMRA_OPCODE for p in packets)
    assert all(p[4:7] == bytes_3(3120001) for p in packets)


def test_embedded_emblc_both_fallback_inject_returns_template() -> None:
    """both fallback inject also rewrites the embedded LC with the template."""
    config = talker_alias_config()
    config["GLOBAL"]["TALKER_ALIAS_MODE"] = "both"
    ta = make_talker_alias_use_cases(config)

    # Legacy both injects the template embedded LC even without fallback_inject.
    assert (
        ta.embedded_emblc_for_stream(
            "MASTER-A",
            bytes_3(3120001),
            bytes_4(0xE6E6E6E6),
            lambda _s, _st: None,
            target_system="MASTER-B",
        )
        is not None
    )
    emblcs = ta.embedded_emblc_for_stream(
        "MASTER-A",
        bytes_3(3120001),
        bytes_4(0xE7E7E7E7),
        lambda _s, _st: None,
        target_system="MASTER-B",
        fallback_inject=True,
    )
    assert emblcs is not None
    blocks, count = emblcs
    assert 1 <= count <= DMRA_BLOCK_COUNT
    assert len(blocks) == count
