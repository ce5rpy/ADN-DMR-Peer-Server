"""Pickle wire helpers for legacy report v1 monitor shim."""

from __future__ import annotations

import pickle
from typing import Any

from .opcodes import REPORT_OPCODES

_PICKLE_PROTOCOL = 2


def encode_bridge_snd_frame(
    bridges: dict[str, Any],
    *,
    protocol: int = _PICKLE_PROTOCOL,
) -> bytes:
    """``BRIDGE_SND`` opcode + ``pickle.dumps(BRIDGES, protocol=2)`` (legacy parity)."""
    return REPORT_OPCODES["BRIDGE_SND"] + pickle.dumps(bridges, protocol=protocol)
