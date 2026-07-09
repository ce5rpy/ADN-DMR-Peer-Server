# ADN DMR Peer Server - UDP receive buffer sizing
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

"""Raise SO_RCVBUF on voice UDP listeners to avoid kernel RcvbufErrors under load."""

from __future__ import annotations

import logging
import socket
from typing import Any

DEFAULT_UDP_RCVBUF = 4 * 1024 * 1024


def udp_rcvbuf_bytes(config: dict[str, Any] | None) -> int:
    if not config:
        return DEFAULT_UDP_RCVBUF
    raw = config.get("GLOBAL", {}).get("UDP_RCVBUF", DEFAULT_UDP_RCVBUF)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return DEFAULT_UDP_RCVBUF
    return raw


def apply_udp_rcvbuf(
    sock: socket.socket,
    requested: int,
    *,
    label: str,
    logger: logging.Logger,
) -> None:
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, requested)
    except OSError as exc:
        logger.warning("(%s) UDP RX buffer not raised (requested %s): %s", label, requested, exc)
        return
    try:
        effective = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    except OSError as exc:
        logger.warning("(%s) UDP RX buffer set but getsockopt failed: %s", label, exc)
        return
    logger.info("(%s) UDP RX buffer raised to %s bytes (requested %s)", label, effective, requested)


__all__ = ["DEFAULT_UDP_RCVBUF", "apply_udp_rcvbuf", "udp_rcvbuf_bytes"]
