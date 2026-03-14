# ADN DMR Peer Server - voice packet generator (legacy mk_voice.pkt_gen)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink (mk_voice.py). GPLv3.

"""Generate HBP DMRD voice packets for a phrase. Legacy mk_voice.pkt_gen."""

from __future__ import annotations

from random import randint
from typing import Any, Iterator

from bitarray import bitarray
from dmr_utils3 import bptc
from dmr_utils3.const import EMB, BS_DATA_SYNC, BS_VOICE_SYNC, LC_OPT, SLOT_TYPE
from dmr_utils3.utils import bytes_4

# Precalculated DMRD byte 15 (slot << 7 | this)
HEADBITS = 0b00100001
BURSTBITS = [0b00010000, 0b00000001, 0b00000010, 0b00000011, 0b00000100, 0b00000101]
TERMBITS = 0b00100010

NULL_EMB_LC = bitarray(endian="big")
NULL_EMB_LC.frombytes(b"\x00\x00\x00\x00")

TAIL = b"\x00\x00"


def pkt_gen(
    rf_src: bytes,
    dst_id: bytes,
    peer: bytes,
    slot: int,
    phrase: list[Any],
) -> Iterator[bytes]:
    """Generate DMRD voice packets for phrase. Each word in phrase is list of [b0, b1] burst pairs (bitarray)."""
    stream_id = bytes_4(randint(0x00, 0xFFFFFFFF))
    sdp = rf_src + dst_id + peer
    lc = LC_OPT + dst_id + rf_src

    head_lc = bptc.encode_header_lc(lc)
    head_lc = [head_lc[:98], head_lc[-98:]]

    term_lc = bptc.encode_terminator_lc(lc)
    term_lc = [term_lc[:98], term_lc[-98:]]

    emb_lc = bptc.encode_emblc(lc)
    embed = [
        BS_VOICE_SYNC,
        EMB["BURST_B"][:8] + emb_lc[1] + EMB["BURST_B"][-8:],
        EMB["BURST_C"][:8] + emb_lc[2] + EMB["BURST_C"][-8:],
        EMB["BURST_D"][:8] + emb_lc[3] + EMB["BURST_D"][-8:],
        EMB["BURST_E"][:8] + emb_lc[4] + EMB["BURST_E"][-8:],
        EMB["BURST_F"][:8] + NULL_EMB_LC + EMB["BURST_F"][-8:],
    ]

    seq = 0
    slot_byte = (slot << 7) & 0xFF

    for _ in range(3):
        pkt = (
            b"DMRD"
            + bytes([seq])
            + sdp
            + bytes([slot_byte | HEADBITS])
            + stream_id
            + (head_lc[0] + SLOT_TYPE["VOICE_LC_HEAD"][:10] + BS_DATA_SYNC + SLOT_TYPE["VOICE_LC_HEAD"][-10:] + head_lc[1]).tobytes()
            + TAIL
        )
        seq = (seq + 1) % 0x100
        yield pkt

    for word in phrase:
        for burst in range(len(word)):
            b0, b1 = word[burst][0], word[burst][1]
            pkt = (
                b"DMRD"
                + bytes([seq])
                + sdp
                + bytes([slot_byte | BURSTBITS[burst % 6]])
                + stream_id
                + (b0 + embed[burst % 6] + b1).tobytes()
                + TAIL
            )
            seq = (seq + 1) % 0x100
            yield pkt

    pkt = (
        b"DMRD"
        + bytes([seq])
        + sdp
        + bytes([slot_byte | TERMBITS])
        + stream_id
        + (term_lc[0] + SLOT_TYPE["VOICE_LC_TERM"][:10] + BS_DATA_SYNC + SLOT_TYPE["VOICE_LC_TERM"][-10:] + term_lc[1]).tobytes()
        + TAIL
    )
    yield pkt
