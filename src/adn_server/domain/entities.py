# ADN DMR Peer Server - domain entities
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
# Derived from ADN DMR Server / FreeDMR  / HBlink. Original license:
###############################################################################
# Copyright (C) 2020 Simon Adlem, G7RZU <g7rzu@gb7fr.org.uk>
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS <n0mjs@me.com>
#
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

"""Domain entities: bridge entry, stream state, system config (mirror legacy BRIDGES/STATUS/CONFIG)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .value_objects import Slot


@dataclass
class BridgeEntry:
    """One system/slot entry in a bridge (legacy BRIDGES[tgid][i])."""

    SYSTEM: str
    TS: Slot
    TGID: bytes  # 3 bytes
    ACTIVE: bool
    TIMEOUT: float | str  # seconds or '' for STAT
    TO_TYPE: str  # 'ON', 'OFF', 'STAT', 'NONE'
    OFF: list[bytes]
    ON: list[bytes]
    RESET: list[Any]
    TIMER: float


@dataclass
class StreamState:
    """Per-slot stream state (legacy STATUS[slot] and per-stream state)."""

    RX_START: float = 0.0
    TX_START: float = 0.0
    RX_SEQ: int = 0
    RX_RFS: bytes = b"\x00"
    TX_RFS: bytes = b"\x00"
    RX_PEER: bytes = b"\x00"
    TX_PEER: bytes = b"\x00"
    RX_STREAM_ID: bytes = b"\x00"
    TX_STREAM_ID: bytes = b"\x00"
    RX_TGID: bytes = b"\x00\x00\x00"
    TX_TGID: bytes = b"\x00\x00\x00"
    RX_TIME: float = 0.0
    TX_TIME: float = 0.0
    RX_TYPE: int = 0
    TX_TYPE: int = 0
    RX_LC: bytes = b"\x00"
    TX_H_LC: bytes = b"\x00"
    TX_T_LC: bytes = b"\x00"
    TX_EMB_LC: dict[int, bytes] = field(default_factory=dict)
    lastSeq: bool = False
    lastData: bool = False
    packets: int = 0
    crcs: set[Any] = field(default_factory=set)


@dataclass
class SystemConfig:
    """Minimal system config for domain (MODE, name, etc.). Full config lives in infrastructure."""

    name: str
    MODE: str  # MASTER, PEER, OPENBRIDGE
    ENABLED: bool = True
