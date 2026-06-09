"""Route MASTER HBP replies through the proxy fan-in UDP socket."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from adn_server.infrastructure.hbp_constants import PRBL


class _DatagramWriter(Protocol):
    def write(self, data: bytes, addr: tuple[str, int]) -> None:
        ...


class ProxyReplyTransport:
    """Wrap the fan-in transport so MASTER replies leave via LISTEN_PORT."""

    def __init__(
        self,
        fanin_transport: _DatagramWriter,
        *,
        prbl_handler: Callable[[bytes, tuple[str, int]], None] | None = None,
    ) -> None:
        self._fanin = fanin_transport
        self._prbl_handler = prbl_handler

    def write(self, data: bytes, addr: tuple[str, int]) -> None:
        if len(data) >= 4 and data[:4] == PRBL and self._prbl_handler is not None:
            self._prbl_handler(data, addr)
            return
        self._fanin.write(data, addr)
