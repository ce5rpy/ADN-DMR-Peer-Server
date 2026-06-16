# ADN DMR Peer Server - infrastructure twisted adapters report pickle legacy
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

"""Pickle wire helpers for legacy report v1 monitor shim."""

from __future__ import annotations

import pickle
from typing import Any

from .opcodes import REPORT_OPCODES

_PICKLE_PROTOCOL = 2


def encode_config_snd_frame(
    systems: dict[str, Any],
    *,
    protocol: int = _PICKLE_PROTOCOL,
) -> bytes:
    """``CONFIG_SND`` opcode + ``pickle.dumps(SYSTEMS, protocol=2)`` (legacy ``hblink.send_config``)."""
    return REPORT_OPCODES["CONFIG_SND"] + pickle.dumps(systems, protocol=protocol)


def encode_bridge_snd_frame(
    bridges: dict[str, Any],
    *,
    protocol: int = _PICKLE_PROTOCOL,
) -> bytes:
    """``BRIDGE_SND`` opcode + ``pickle.dumps(BRIDGES, protocol=2)`` (legacy parity)."""
    return REPORT_OPCODES["BRIDGE_SND"] + pickle.dumps(bridges, protocol=protocol)
