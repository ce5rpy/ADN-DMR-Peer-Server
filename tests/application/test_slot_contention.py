# ADN DMR Peer Server - slot contention helpers
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations


from adn_server.application.routing.helpers import (
    hbp_ingress_new_stream_collision,
    hbp_slot_blocks_group_voice,
    hbp_slot_blocks_group_voice_for_peer,
    slot_has_active_voice,
    slot_in_group_hangtime,
)
from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD, HBPF_SLT_VTERM, STREAM_TO

_TG_A = bytes_3(7144)
_TG_B = bytes_3(730444)
_STREAM_A = bytes_4(0x11111111)
_STREAM_B = bytes_4(0x22222222)


def _active_rx_slot(tgid: bytes = _TG_A, stream_id: bytes = _STREAM_A, t: float = 1_000_000.0) -> dict:
    return {
        "RX_TYPE": HBPF_SLT_VHEAD,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": tgid,
        "RX_TIME": t,
        "RX_STREAM_ID": stream_id,
        "TX_TIME": 0.0,
    }


def test_active_slot_blocks_other_tg_even_with_zero_hangtime() -> None:
    now = 1_000_000.0
    slot = _active_rx_slot()
    assert slot_has_active_voice(slot, now + 0.1)
    assert hbp_slot_blocks_group_voice(slot, _TG_B, _STREAM_B, now + 0.1, 0.0)


def test_same_stream_allowed_during_active_qso() -> None:
    now = 1_000_000.0
    slot = _active_rx_slot()
    assert not hbp_slot_blocks_group_voice(slot, _TG_A, _STREAM_A, now + 0.1, 0.0)


def test_ingress_same_subscriber_rekey_allowed() -> None:
    """Legacy: same RF source may open a new stream while the prior is still open."""
    now = 1_000_000.0
    rf = bytes_3(3120001)
    slot = _active_rx_slot(stream_id=_STREAM_A, t=now)
    slot["RX_RFS"] = rf
    assert not hbp_ingress_new_stream_collision(
        slot, bytes_4(1001), rf, _STREAM_B, now + 0.1, per_peer=False,
    )


def test_per_peer_scope_ignores_other_hotspot_busy_slot() -> None:
    """Inject-only: peer B must not inherit slot contention from peer A."""
    now = 1_000_000.0
    peer_a = bytes_4(352000133)
    peer_b = bytes_4(714002301)
    slot = _active_rx_slot()
    slot["RX_PEER"] = peer_a
    assert hbp_slot_blocks_group_voice_for_peer(
        slot, peer_b, _TG_B, _STREAM_B, now + 0.1, 0.0, per_peer=True,
    ) is False
    assert hbp_slot_blocks_group_voice_for_peer(
        slot, peer_a, _TG_B, _STREAM_B, now + 0.1, 0.0, per_peer=True,
    ) is True


def test_global_scope_still_blocks_any_peer_on_busy_slot() -> None:
    now = 1_000_000.0
    peer_b = bytes_4(714002301)
    slot = _active_rx_slot()
    slot["RX_PEER"] = bytes_4(352000133)
    assert hbp_slot_blocks_group_voice_for_peer(
        slot, peer_b, _TG_B, _STREAM_B, now + 0.1, 0.0, per_peer=False,
    ) is True

    now = 1_000_000.0
    slot = {"RX_TYPE": HBPF_SLT_VTERM, "TX_TYPE": HBPF_SLT_VTERM, "RX_TIME": 0.0, "TX_TIME": 0.0}
    assert not hbp_slot_blocks_group_voice(slot, _TG_B, _STREAM_B, now, 5.0)


def test_group_hangtime_blocks_other_tg_after_vterm() -> None:
    now = 1_000_000.0
    slot = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": _TG_A,
        "RX_TIME": now,
        "TX_TGID": _TG_A,
        "TX_TIME": now,
    }
    assert slot_in_group_hangtime(slot, _TG_B, now + 2.0, 5.0)
    assert not slot_in_group_hangtime(slot, _TG_A, now + 2.0, 5.0)
    assert not slot_in_group_hangtime(slot, _TG_B, now + 6.0, 5.0)


def test_group_hangtime_zero_allows_other_tg_after_vterm() -> None:
    now = 1_000_000.0
    slot = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": _TG_A,
        "RX_TIME": now,
        "TX_TGID": _TG_A,
        "TX_TIME": now,
    }
    assert not slot_in_group_hangtime(slot, _TG_B, now + 1.0, 0.0)
    assert not hbp_slot_blocks_group_voice(slot, _TG_B, _STREAM_B, now + 1.0, 0.0)


def test_active_tx_leg_blocks_other_stream() -> None:
    now = 1_000_000.0
    slot = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TGID": _TG_A,
        "TX_TIME": now,
        "TX_STREAM_ID": _STREAM_A,
    }
    assert slot_has_active_voice(slot, now + 0.05)
    assert hbp_slot_blocks_group_voice(slot, _TG_B, _STREAM_B, now + 0.05, 0.0)


def test_stream_timeout_ends_active_busy() -> None:
    now = 1_000_000.0
    slot = _active_rx_slot(t=now - STREAM_TO - 0.01)
    assert not slot_has_active_voice(slot, now)
