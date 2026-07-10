# ADN DMR Peer Server - server broadcast slot contention
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations

from adn_server.application.routing.helpers import (
    hbp_slot_blocks_group_voice,
    master_slot_holds_server_broadcast,
)
from adn_server.domain import HBPF_SLT_VHEAD, HBPF_SLT_VTERM, STREAM_TO, bytes_3, bytes_4


def test_master_slot_holds_server_broadcast_detects_announcement_row() -> None:
    slot = {
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": 100.0,
        "TX_RFS": bytes_3(5000),
        "TX_TGID": bytes_3(91),
    }
    assert master_slot_holds_server_broadcast(slot, 100.1) is True
    assert master_slot_holds_server_broadcast(slot, 100.0 + STREAM_TO + 1) is False


def test_master_slot_holds_server_broadcast_ignores_obp_tx() -> None:
    slot = {
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": 100.0,
        "TX_RFS": bytes_3(3340062),
        "TX_TGID": bytes_3(7144),
    }
    assert master_slot_holds_server_broadcast(slot, 100.1) is False


def test_obp_blocked_when_server_broadcast_holds_slot() -> None:
    slot = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": 200.0,
        "TX_RFS": bytes_3(5000),
        "TX_TGID": bytes_3(91),
    }
    blocked = hbp_slot_blocks_group_voice(
        slot,
        bytes_3(7144),
        bytes_4(0x11111111),
        200.05,
        group_hangtime=3.0,
    )
    assert blocked is True
