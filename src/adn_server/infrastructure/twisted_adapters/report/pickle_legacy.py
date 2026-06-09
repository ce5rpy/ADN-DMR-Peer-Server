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
