# ADN DMR Peer Server - bridge router implementation
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from ADN DMR Server / HBlink. GPLv3.

"""In-memory BRIDGES and ACL check (legacy acl_check)."""

from __future__ import annotations

from typing import Any

from ..application.ports import BridgeRouter


def _int_id(val: bytes | int) -> int:
    if isinstance(val, int):
        return val
    if len(val) >= 4:
        return int.from_bytes(val[:4], "big")
    if len(val) == 3:
        return int.from_bytes(val, "big")
    return 0


class InMemoryBridgeRouter(BridgeRouter):
    """Holds BRIDGES dict; implements acl_check like legacy."""

    def __init__(self) -> None:
        self._bridges: dict[str, list[dict[str, Any]]] = {}

    def get_bridges(self) -> dict[str, list[dict[str, Any]]]:
        return self._bridges

    def set_bridges(self, bridges: dict[str, list[dict[str, Any]]]) -> None:
        self._bridges = bridges

    def acl_check(self, id_bytes_or_int: bytes | int, acl: tuple[bool, list[tuple[int, int]]]) -> bool:
        """Legacy acl_check: (action, ranges). If id in any range return action else not action."""
        action, ranges = acl
        i = _int_id(id_bytes_or_int)
        for lo, hi in ranges:
            if lo <= i <= hi:
                return action
        return not action
