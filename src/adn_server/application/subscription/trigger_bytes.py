"""Normalize legacy BRIDGES ON/OFF/RESET lists to bytes tuples."""

from __future__ import annotations

from typing import Any

from adn_server.domain import bytes_3, int_id


def trigger_bytes_tuple(items: Any) -> tuple[bytes, ...]:
    if not items:
        return ()
    out: list[bytes] = []
    for item in items:
        if isinstance(item, bytes):
            out.append(item[:3].ljust(3, b"\x00") if len(item) >= 3 else bytes_3(int_id(item)))
        elif isinstance(item, int):
            out.append(bytes_3(item))
    return tuple(out)


def dst_in_triggers(dst_id_b: bytes, dst_group: int, triggers: tuple[bytes, ...]) -> bool:
    if dst_id_b in triggers:
        return True
    return any(int_id(item) == dst_group for item in triggers)
