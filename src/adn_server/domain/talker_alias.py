# ADN DMR Peer Server - DMR Talker Alias (ETSI / MMDVMHost)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Talker Alias encode/decode and HBP DMRA packet builders (UTF-8 format 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bitarray import bitarray

TALKER_ALIAS_MAX_LEN = 29
TA_FORMAT_7BIT = 0
TA_FORMAT_ISO8 = 1
TA_FORMAT_UTF8 = 2
DMRA_OPCODE = b"DMRA"
DMRA_PACKET_LEN = 15
DMRA_BLOCK_COUNT = 4
DMRA_PAYLOAD_LEN = 7
DMRA_BUF_LEN = DMRA_BLOCK_COUNT * DMRA_PAYLOAD_LEN
FLCO_TALKER_ALIAS_HEADER = 4
FLCO_TALKER_ALIAS_BLOCK3 = 7
TA_EMB_LC_LEN = 9


def truncate_talker_alias(text: str) -> str:
    """Hard-cap at protocol maximum (not user-configurable)."""
    if len(text) <= TALKER_ALIAS_MAX_LEN:
        return text
    return text[:TALKER_ALIAS_MAX_LEN]


def decode_ta(buf: bytes) -> str:
    """Decode 28-byte TA buffer (formats 0–3). Mirrors MMDVMHost CDMRTA::decodeTA."""
    if len(buf) < 1:
        return ""
    ta_format = (buf[0] >> 6) & 0x03
    ta_size = (buf[0] >> 1) & 0x1F
    if ta_format == 1 or ta_format == 2:
        raw = buf[1 : 1 + ta_size]
        return raw.decode("latin-1", errors="replace")
    if ta_format != 0:
        return ""
    out = bytearray()
    t1 = 0
    t2 = 0
    c = 0
    for i in range(min(32, len(buf))):
        if t2 >= ta_size:
            break
        for j in range(7, -1, -1):
            c = ((c << 1) | ((buf[i] >> j) & 1)) & 0xFF
            t1 += 1
            if t1 == 7:
                if i > 0:
                    out.append(c & 0x7F)
                    t2 += 1
                    if t2 >= ta_size:
                        break
                t1 = 0
                c = 0
    return out[:ta_size].decode("ascii", errors="replace")


decode_7bit = decode_ta  # backwards-compatible alias


def encode_utf8(text: str) -> bytes:
    """Encode text into 28-byte TA buffer (format 2 / UTF-8)."""
    text = truncate_talker_alias(text)
    raw = text.encode("utf-8")
    if len(raw) > 27:
        raw = truncate_talker_alias(text.encode("utf-8")[:27].decode("utf-8", errors="ignore")).encode("utf-8")
    size = len(raw)
    header = (TA_FORMAT_UTF8 << 6) | (size << 1) | 0
    buf = bytearray(DMRA_BUF_LEN)
    buf[0] = header
    buf[1 : 1 + size] = raw
    return bytes(buf)


def encode_7bit(text: str) -> bytes:
    """Encode text into 28-byte TA buffer (format 0 / 7-bit)."""
    text = truncate_talker_alias(text)
    size = len(text)
    bits: list[int] = []
    for b in (0, 0):
        bits.append(b)
    for b in range(4, -1, -1):
        bits.append((size >> b) & 1)
    for ch in text:
        v = ord(ch) & 0x7F
        for b in range(6, -1, -1):
            bits.append((v >> b) & 1)
    while len(bits) < DMRA_BUF_LEN * 8:
        bits.append(0)
    buf = bytearray(DMRA_BUF_LEN)
    for i in range(DMRA_BUF_LEN):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i * 8 + j]
        buf[i] = byte
    return bytes(buf)


def blocks_from_buffer(buf: bytes) -> list[bytes]:
    """Split 28-byte encoded buffer into four 7-byte DMRA payloads."""
    buf = buf.ljust(DMRA_BUF_LEN, b"\x00")[:DMRA_BUF_LEN]
    return [buf[i * DMRA_PAYLOAD_LEN : (i + 1) * DMRA_PAYLOAD_LEN] for i in range(DMRA_BLOCK_COUNT)]


def required_ta_block_count(buf: bytes) -> int:
    """Blocks 1–4 actually needed (skip trailing zero payloads). ETSI allows 1–4."""
    blocks = blocks_from_buffer(buf)
    last = 0
    for i in range(DMRA_BLOCK_COUNT):
        if blocks[i] != b"\x00" * DMRA_PAYLOAD_LEN:
            last = i
    return max(1, last + 1)


def buffer_from_blocks(blocks: dict[int, bytes]) -> bytes:
    """Merge up to four block payloads into a 28-byte buffer (ADN inject layout)."""
    buf = bytearray(DMRA_BUF_LEN)
    for block_id, payload in blocks.items():
        if 0 <= block_id < DMRA_BLOCK_COUNT and payload:
            start = block_id * DMRA_PAYLOAD_LEN
            buf[start : start + DMRA_PAYLOAD_LEN] = payload[:DMRA_PAYLOAD_LEN]
    return bytes(buf)


def buffer_from_wire_blocks(blocks: dict[int, bytes]) -> bytes:
    """Merge MMDVMHost DMRA wire payloads into the 28-byte TA buffer.

    ``writeTalkerAlias`` copies ``data + 2`` (7 bytes) from the 9-byte embedded LC;
    ``CDMRTA::add(blockId, data + 2, 7)`` stores those at ``m_buf[blockId * 7]``.
    The UDP payload is therefore the same layout as ``buffer_from_blocks``.
    """
    return buffer_from_blocks(blocks)


def is_ta_header_byte(byte0: int) -> bool:
    """True if byte looks like ETSI TA header (UTF-8/ISO formats; not 7-bit)."""
    if (byte0 & 1) != 0:
        return False
    fmt = (byte0 >> 6) & 0x03
    size = (byte0 >> 1) & 0x1F
    return fmt in (1, 2) and 1 <= size <= TALKER_ALIAS_MAX_LEN


def talker_alias_decode_complete(buf: bytes) -> bool:
    """True when TA buffer decodes with expected size (MMDVM DMRTA parity)."""
    if len(buf) < 1 or not is_ta_header_byte(buf[0]):
        return False
    ta_size = (buf[0] >> 1) & 0x1F
    text = decode_ta(buf).rstrip("\x00").strip()
    return len(text) >= ta_size


def decode_ta_from_blocks(blocks: dict[int, bytes]) -> str:
    """Decode TA from buffered DMRA blocks (MMDVM wire layout, then ADN layout)."""
    buf = buffer_from_wire_blocks(blocks)
    if talker_alias_decode_complete(buf):
        return decode_ta(buf).rstrip("\x00").strip()
    if blocks.get(0) and is_ta_header_byte(blocks[0][0]):
        buf = buffer_from_blocks(blocks)
        if talker_alias_decode_complete(buf):
            return decode_ta(buf).rstrip("\x00").strip()
    return ""


def build_dmra_packets(rf_src: bytes, text: str) -> list[bytes]:
    """Build HBP DMRA packets (1–4) for server injection."""
    rf = rf_src[:3] if len(rf_src) >= 3 else rf_src.ljust(3, b"\x00")[:3]
    encoded = encode_utf8(text)
    blocks = blocks_from_buffer(encoded)
    count = required_ta_block_count(encoded)
    packets: list[bytes] = []
    for block_id in range(count):
        packets.append(DMRA_OPCODE + rf + bytes([block_id]) + blocks[block_id])
    return packets


def build_dmra_packet(rf_src: bytes, block_id: int, payload: bytes) -> bytes:
    """Build one 15-byte DMRA packet (pass-through or re-encode block)."""
    rf = rf_src[:3] if len(rf_src) >= 3 else rf_src.ljust(3, b"\x00")[:3]
    block = max(0, min(3, int(block_id)))
    pl = payload[:DMRA_PAYLOAD_LEN].ljust(DMRA_PAYLOAD_LEN, b"\x00")
    return DMRA_OPCODE + rf + bytes([block]) + pl


def parse_dmra_packet(data: bytes) -> tuple[bytes, int, bytes] | None:
    """Parse MMDVMHost HBP DMRA (15 bytes), per ``DMRNetwork::writeTalkerAlias``.

    Layout: ``DMRA`` | src_id[24-bit BE @4–6] | type @7 (0–3) | memcpy(@8, data+2, 7).

    ``data`` is the 9-byte embedded LC (``CDMREmbeddedData::getRawData``); wire bytes equal
    ``CDMRTA::add(blockId, data+2, 7)`` → ``m_buf[blockId*7 : blockId*7+7]``.
    """
    if len(data) < DMRA_PACKET_LEN or data[:4] != DMRA_OPCODE:
        return None
    block_id = data[7]
    if block_id > 3:
        return None
    return data[4:7], block_id, data[8:15]


def store_ta_block(blocks: dict[int, bytes], block_id: int, payload: bytes) -> bool:
    """Store one wire fragment (7 bytes at ``m_buf[block_id*7]``)."""
    if block_id < 0 or block_id > 3:
        return False
    blocks[block_id] = payload[:DMRA_PAYLOAD_LEN]
    return True


def store_ta_from_embed_lc(blocks: dict[int, bytes], block_id: int, lc9: bytes) -> bool:
    """Store from 9-byte embedded LC (MMDVM ``data`` in ``DMRSlot`` TA FLCO 4–7 path)."""
    if block_id < 0 or block_id > 3 or len(lc9) < 9:
        return False
    return store_ta_block(blocks, block_id, lc9[2:9])


def talker_alias_block_id_from_lc(lc: bytes) -> int | None:
    """FLCO 4–7 (MMDVM TALKER_ALIAS_HEADER..BLOCK3) → block index 0–3, else None."""
    if len(lc) < 9:
        return None
    flco = lc[0]
    if flco < FLCO_TALKER_ALIAS_HEADER or flco > FLCO_TALKER_ALIAS_BLOCK3:
        return None
    return flco - FLCO_TALKER_ALIAS_HEADER


def try_buffer_ta_from_voice_fragments(
    acc: dict[int, "bitarray"],
    vseq: int,
    dmrpkt: bytes,
    blocks: dict[int, bytes],
) -> bool:
    """Reassemble embedded LC across voice bursts B–E (vseq 1–4) and store if it is a TA.

    ``dmr_utils3.bptc.decode_emblc`` is correct on properly FEC-encoded input (the encode
    helper is the buggy one), so a TA sent by a real radio decodes losslessly here.
    Returns True when a TA block was decoded and stored.
    """
    from dmr_utils3 import bptc, decode

    if vseq not in (1, 2, 3, 4) or len(dmrpkt) < 33:
        return False
    try:
        embed = decode.voice(dmrpkt)["EMBED"]
    except Exception:
        return False
    if vseq == 1:
        acc.clear()
    acc[vseq] = embed
    if not all(i in acc for i in (1, 2, 3, 4)):
        return False
    try:
        lc = bptc.decode_emblc(acc[1] + acc[2] + acc[3] + acc[4])
    except Exception:
        acc.clear()
        return False
    acc.clear()
    block_id = talker_alias_block_id_from_lc(lc)
    if block_id is None:
        return False
    return store_ta_from_embed_lc(blocks, block_id, lc)


def talker_alias_lc_bytes(block_id: int, payload7: bytes) -> bytes:
    """Build 9-byte embedded LC for one TA fragment (FLCO 4–7 + FID + 7 payload)."""
    block = max(0, min(3, int(block_id)))
    payload = payload7[:DMRA_PAYLOAD_LEN].ljust(DMRA_PAYLOAD_LEN, b"\x00")
    return bytes([FLCO_TALKER_ALIAS_HEADER + block, 0x00]) + payload


def encode_emblc(_lc: bytes) -> dict[int, bitarray]:
    """Embedded-LC BPTC encode with the ``dmr_utils3`` bug fixed.

    Upstream ``dmr_utils3.bptc.encode_emblc`` builds segment D's second row from
    ``_binlc[24]`` instead of ``_binlc[25]`` (duplicating bit 24, dropping bit 25), which
    corrupts one bit of the embedded LC (e.g. injected ``Rodrigo`` decodes as ``Rodrigg``).
    This is a faithful copy with that single index corrected, so injected Talker Alias
    round-trips losslessly through ``decode_emblc`` and on real radios.
    """
    from bitarray import bitarray
    from dmr_utils3 import crc, hamming

    _csum = crc.csum5(_lc)
    _binlc = bitarray(endian="big")
    _binlc.frombytes(_lc)
    _binlc.insert(32, _csum[0])
    _binlc.insert(43, _csum[1])
    _binlc.insert(54, _csum[2])
    _binlc.insert(65, _csum[3])
    _binlc.insert(76, _csum[4])
    for index in range(0, 112, 16):
        for hindex, hbit in zip(
            range(index + 11, index + 16), hamming.enc_16114(_binlc[index:index + 11])
        ):
            _binlc.insert(hindex, hbit)
    for index in range(0, 16):
        _binlc.insert(
            index + 112,
            _binlc[index] ^ _binlc[index + 16] ^ _binlc[index + 32] ^ _binlc[index + 48]
            ^ _binlc[index + 64] ^ _binlc[index + 80] ^ _binlc[index + 96],
        )

    def _seg(rows: tuple[tuple[int, ...], ...]) -> bitarray:
        out = bitarray(endian="big")
        for row in rows:
            out.extend([_binlc[i] for i in row])
        return out

    emblc_b = _seg((
        (0, 16, 32, 48, 64, 80, 96, 112),
        (1, 17, 33, 49, 65, 81, 97, 113),
        (2, 18, 34, 50, 66, 82, 98, 114),
        (3, 19, 35, 51, 67, 83, 99, 115),
    ))
    emblc_c = _seg((
        (4, 20, 36, 52, 68, 84, 100, 116),
        (5, 21, 37, 53, 69, 85, 101, 117),
        (6, 22, 38, 54, 70, 86, 102, 118),
        (7, 23, 39, 55, 71, 87, 103, 119),
    ))
    emblc_d = _seg((
        (8, 24, 40, 56, 72, 88, 104, 120),
        (9, 25, 41, 57, 73, 89, 105, 121),  # fixed: bit 25 (dmr_utils3 wrongly uses 24)
        (10, 26, 42, 58, 74, 90, 106, 122),
        (11, 27, 43, 59, 75, 91, 107, 123),
    ))
    emblc_e = _seg((
        (12, 28, 44, 60, 76, 92, 108, 124),
        (13, 29, 45, 61, 77, 93, 109, 125),
        (14, 30, 46, 62, 78, 94, 110, 126),
        (15, 31, 47, 63, 79, 95, 111, 127),
    ))
    return {1: emblc_b, 2: emblc_c, 3: emblc_d, 4: emblc_e}


def encode_talker_alias_emblc(text: str) -> tuple[list[dict[int, bitarray]], int]:
    """Embedded-LC dicts for TA blocks 0..N-1 and block count N (1–4)."""
    encoded = encode_utf8(text)
    blocks = blocks_from_buffer(encoded)
    count = required_ta_block_count(encoded)
    emblcs = [encode_emblc(talker_alias_lc_bytes(i, blocks[i])) for i in range(count)]
    return emblcs, count


def encode_talker_alias_emblc_from_blocks(blocks: dict[int, bytes]) -> tuple[list[dict[int, bitarray]], int]:
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
