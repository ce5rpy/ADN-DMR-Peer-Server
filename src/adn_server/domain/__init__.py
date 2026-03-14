# ADN DMR Peer Server - domain layer
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

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
