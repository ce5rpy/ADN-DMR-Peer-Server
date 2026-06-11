"""Shared helpers for bridge unit-data tests."""

from __future__ import annotations

from adn_server.domain.hbp_protocol import HBPF_SLT_VTERM


def idle_hbp_slot() -> dict:
    return {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "TX_TIME": 0.0,
    }
