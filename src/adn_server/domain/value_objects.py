# ADN DMR Peer Server - value objects
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

"""Value objects: DMR IDs, slot, call type, etc. (mirror legacy const and types)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Legacy ID_MIN=1, ID_MAX=16776415, PEER_MAX=4294967295
ID_MIN = 1
ID_MAX = 16776415
PEER_MAX = 4294967295


@dataclass(frozen=True, slots=True)
class DmrId:
    """DMR subscriber/peer/talkgroup numeric ID."""

    value: int

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True, slots=True)
class TgId:
    """Talkgroup ID (same numeric space as DmrId for group calls)."""

    value: int

    def __int__(self) -> int:
        return self.value


Slot = Literal[1, 2]
"""Timeslot 1 or 2."""

CallType = Literal["unit", "group"]
"""Unit (private) or group call."""


def bytes_3(i: int) -> bytes:
    """Encode int as 3-byte big-endian (legacy bytes_3)."""
    return (int(i) & 0xFFFFFF).to_bytes(3, "big")


def bytes_4(i: int) -> bytes:
    """Encode int as 4-byte big-endian (legacy bytes_4, salt, peer_id in packets)."""
    return (int(i) & 0xFFFFFFFF).to_bytes(4, "big")


def int_id(val: bytes | int) -> int:
    """Decode 3- or 4-byte big-endian to int (legacy int_id)."""
    if isinstance(val, int):
        return val
    if len(val) >= 4:
        return int.from_bytes(val[:4], "big")
    if len(val) == 3:
        return int.from_bytes(val, "big")
    return 0
