"""Tests for UDP receive buffer helper."""

from __future__ import annotations

import logging
import socket
from unittest.mock import MagicMock

from adn_server.infrastructure.udp_rcvbuf import (
    DEFAULT_UDP_RCVBUF,
    apply_udp_rcvbuf,
    udp_rcvbuf_bytes,
)


def test_udp_rcvbuf_bytes_default() -> None:
    assert udp_rcvbuf_bytes(None) == DEFAULT_UDP_RCVBUF
    assert udp_rcvbuf_bytes({}) == DEFAULT_UDP_RCVBUF
    assert udp_rcvbuf_bytes({"GLOBAL": {}}) == DEFAULT_UDP_RCVBUF


def test_udp_rcvbuf_bytes_from_config() -> None:
    assert udp_rcvbuf_bytes({"GLOBAL": {"UDP_RCVBUF": 2097152}}) == 2097152


def test_udp_rcvbuf_bytes_rejects_invalid() -> None:
    assert udp_rcvbuf_bytes({"GLOBAL": {"UDP_RCVBUF": 0}}) == DEFAULT_UDP_RCVBUF
    assert udp_rcvbuf_bytes({"GLOBAL": {"UDP_RCVBUF": -1}}) == DEFAULT_UDP_RCVBUF
    assert udp_rcvbuf_bytes({"GLOBAL": {"UDP_RCVBUF": "big"}}) == DEFAULT_UDP_RCVBUF
    assert udp_rcvbuf_bytes({"GLOBAL": {"UDP_RCVBUF": True}}) == DEFAULT_UDP_RCVBUF


def test_apply_udp_rcvbuf_sets_socket_buffer() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        requested = 2 * 1024 * 1024
        log = MagicMock(spec=logging.Logger)
        apply_udp_rcvbuf(sock, requested, label="TEST", logger=log)
        effective = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        assert effective >= requested
        log.info.assert_called_once()
        args = log.info.call_args[0]
        assert args[0] == "(%s) UDP RX buffer raised to %s bytes (requested %s)"
        assert args[1] == "TEST"
        assert args[2] == effective
        assert args[3] == requested
    finally:
        sock.close()
