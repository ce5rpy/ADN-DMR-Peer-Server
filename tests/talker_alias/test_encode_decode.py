# ADN DMR Peer Server - tests talker alias encode decode
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

"""Talker Alias domain encode/decode roundtrips."""

from __future__ import annotations

from adn_server.domain.talker_alias import (
    buffer_from_blocks,
    decode_7bit,
    decode_ta,
    encode_7bit,
    encode_iso8,
    encode_utf8,
    parse_ta_text_formats,
    required_ta_block_count,
    truncate_talker_alias,
)
from adn_server.infrastructure.talker_alias_emblc import encode_talker_alias_emblc


def test_truncate_talker_alias_caps_at_29() -> None:
    long_text = "A" * 40
    assert len(truncate_talker_alias(long_text)) == 29


def test_encode_utf8_roundtrip() -> None:
    text = "CE5RPY Rodrigo"
    assert decode_7bit(encode_utf8(text)) == text


def test_encode_7bit_roundtrip() -> None:
    text = "CE5RPY"
    assert decode_7bit(encode_7bit(text)) == text


def test_required_ta_block_count_skips_trailing_zeros() -> None:
    buf = encode_utf8("Hi")
    assert 1 <= required_ta_block_count(buf) <= 4


def test_buffer_from_blocks_merges_payloads() -> None:
    blocks = {0: b"\x01" * 7, 1: b"\x02" * 7}
    buf = buffer_from_blocks(blocks)
    assert buf[:7] == b"\x01" * 7
    assert buf[7:14] == b"\x02" * 7


def test_encode_iso8_roundtrip() -> None:
    text = "CE5RPY Niño"
    assert decode_ta(encode_iso8(text)) == text


def test_parse_ta_text_formats_comma_list() -> None:
    assert parse_ta_text_formats("utf8, iso8") == ["utf8", "iso8"]


def test_multi_format_emblc_concatenates() -> None:
    single, _ = encode_talker_alias_emblc("Hi", ("utf8",))
    dual, n = encode_talker_alias_emblc("Hi", ("utf8", "iso8"))
    assert n == len(dual)
    assert len(dual) > len(single)
