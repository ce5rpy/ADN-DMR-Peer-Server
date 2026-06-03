# ADN DMR Peer Server - DMR BPTC embedded LC (dmr_utils3 adapter)
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

"""Corrected embedded-LC BPTC encoder (drop-in for ``dmr_utils3.bptc.encode_emblc``)."""

from __future__ import annotations

from bitarray import bitarray
from dmr_utils3 import crc, hamming


def encode_emblc(lc: bytes) -> dict[int, bitarray]:
    """Encode a 9-byte embedded LC into burst B–E fragment dicts {1..4: bitarray}.

    Upstream ``dmr_utils3.bptc.encode_emblc`` uses ``_binlc[24]`` twice in segment D row 2
    instead of ``_binlc[25]``, which can corrupt one bit (e.g. Talker Alias ``Rodrigo`` →
    ``Rodrigg``). This copy matches upstream except for that index, so decode on radios and
    ``dmr_utils3.bptc.decode_emblc`` stay aligned.

    Use this everywhere ADN generates embedded LC (bridge group LC, TA overlay, parrot).
    """
    _csum = crc.csum5(lc)
    _binlc = bitarray(endian="big")
    _binlc.frombytes(lc)
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
