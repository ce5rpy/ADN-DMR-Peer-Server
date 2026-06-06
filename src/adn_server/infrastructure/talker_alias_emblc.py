# ADN DMR Peer Server - Talker Alias embedded LC wire encoding
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Build embedded-LC burst dicts for Talker Alias (uses domain TA rules + domain DMR BPTC)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..domain.talker_alias import (
    blocks_from_buffer,
    buffer_from_blocks,
    buffer_from_wire_blocks,
    encode_ta_buffer,
    is_ta_header_byte,
    required_ta_block_count,
    talker_alias_decode_complete,
    talker_alias_lc_bytes,
)
from ..domain.dmr.bptc import encode_emblc

if TYPE_CHECKING:
    from bitarray import bitarray


def encode_talker_alias_emblc(
    text: str,
    text_formats: Sequence[str] | str = ("utf8",),
) -> tuple[list[dict[int, bitarray]], int]:
    """Embedded-LC dicts for TA blocks; multiple encodings are emitted back-to-back."""
    if isinstance(text_formats, str):
        formats: list[str] = [text_formats]
    else:
        formats = list(text_formats) or ["utf8"]
    emblcs: list[dict[int, bitarray]] = []
    for tf in formats:
        encoded = encode_ta_buffer(text, tf)
        blocks = blocks_from_buffer(encoded)
        count = required_ta_block_count(encoded)
        emblcs += [encode_emblc(talker_alias_lc_bytes(i, blocks[i])) for i in range(count)]
    return emblcs, len(emblcs)


def encode_talker_alias_emblc_from_blocks(
    blocks: dict[int, bytes],
) -> tuple[list[dict[int, bitarray]], int]:
    """Build embedded TA LC dicts from buffered DMRA wire payloads."""
    buf = buffer_from_wire_blocks(blocks)
    count = required_ta_block_count(buf)
    if not talker_alias_decode_complete(buf) and blocks.get(0) and is_ta_header_byte(blocks[0][0]):
        buf = buffer_from_blocks(blocks)
        count = required_ta_block_count(buf)
    emblcs = [
        encode_emblc(talker_alias_lc_bytes(i, blocks[i]))
        for i in range(count)
        if i in blocks
    ]
    return emblcs, count


class DefaultTalkerAliasEmblcEncoder:
    """Infrastructure adapter for ``TalkerAliasEmblcEncoder`` (wired from ``main``)."""

    def encode_text(
        self,
        text: str,
        *,
        text_formats: Sequence[str] | None = None,
    ) -> tuple[list[dict[int, bitarray]], int]:
        fmts: Sequence[str] = text_formats if text_formats is not None else ("utf8",)
        return encode_talker_alias_emblc(text, fmts)

    def encode_blocks(self, blocks: dict[int, bytes]) -> tuple[list[dict[int, bitarray]], int]:
        return encode_talker_alias_emblc_from_blocks(blocks)


default_ta_emblc_encoder = DefaultTalkerAliasEmblcEncoder()
