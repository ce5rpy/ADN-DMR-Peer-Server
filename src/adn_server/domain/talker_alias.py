# ADN DMR Peer Server - DMR Talker Alias (ETSI / MMDVMHost)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Talker Alias encode/decode and HBP DMRA packet builders (UTF-8 format 2)."""

from __future__ import annotations

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
    """Merge up to four block payloads into a 28-byte buffer."""
    buf = bytearray(DMRA_BUF_LEN)
    for block_id, payload in blocks.items():
        if 0 <= block_id < DMRA_BLOCK_COUNT and payload:
            start = block_id * DMRA_PAYLOAD_LEN
            buf[start : start + DMRA_PAYLOAD_LEN] = payload[:DMRA_PAYLOAD_LEN]
    return bytes(buf)


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
    """Parse DMRA packet; returns (rf_src, block_id, payload) or None."""
    if len(data) < DMRA_PACKET_LEN or data[:4] != DMRA_OPCODE:
        return None
    rf_src = data[4:7]
    block_id = data[7]
    payload = data[8:15]
    return rf_src, block_id, payload


def talker_alias_lc_bytes(block_id: int, payload7: bytes) -> bytes:
    """Build 9-byte embedded LC for one TA fragment (FLCO 4–7 + FID + 7 payload)."""
    block = max(0, min(3, int(block_id)))
    payload = payload7[:DMRA_PAYLOAD_LEN].ljust(DMRA_PAYLOAD_LEN, b"\x00")
    return bytes([FLCO_TALKER_ALIAS_HEADER + block, 0x00]) + payload


def encode_talker_alias_emblc(text: str) -> tuple[list[dict[int, "bitarray.bitarray"]], int]:
    """Embedded-LC dicts for TA blocks 0..N-1 and block count N (1–4)."""
    from dmr_utils3 import bptc

    encoded = encode_utf8(text)
    blocks = blocks_from_buffer(encoded)
    count = required_ta_block_count(encoded)
    emblcs = [bptc.encode_emblc(talker_alias_lc_bytes(i, blocks[i])) for i in range(count)]
    return emblcs, count


def encode_talker_alias_emblc_from_blocks(blocks: dict[int, bytes]) -> tuple[list[dict[int, "bitarray.bitarray"]], int]:
    """Build embedded TA LC dicts from buffered DMRA payloads."""
    from dmr_utils3 import bptc

    buf = buffer_from_blocks(blocks)
    buf_blocks = blocks_from_buffer(buf)
    count = required_ta_block_count(buf)
    emblcs = [bptc.encode_emblc(talker_alias_lc_bytes(i, buf_blocks[i])) for i in range(count)]
    return emblcs, count
