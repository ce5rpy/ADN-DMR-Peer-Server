# ADN DMR Peer Server - domain layer
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

from .entities import BridgeEntry, StreamState, SystemConfig
from .value_objects import DmrId, TgId, Slot, CallType, bytes_3, bytes_4, int_id, ID_MIN, ID_MAX, PEER_MAX
from .errors import DomainError, ConfigError, ACLError
from .result import Result, Success, Fail, is_fail, is_ok, unwrap_or

__all__ = [
    "BridgeEntry",
    "StreamState",
    "SystemConfig",
    "DmrId",
    "TgId",
    "Slot",
    "CallType",
    "bytes_3",
    "bytes_4",
    "int_id",
    "ID_MIN",
    "ID_MAX",
    "PEER_MAX",
    "DomainError",
    "ConfigError",
    "ACLError",
    "Result",
    "Success",
    "Fail",
    "is_fail",
    "is_ok",
    "unwrap_or",
]
