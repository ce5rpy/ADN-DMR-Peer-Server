# ADN DMR Peer Server - peer RF mode (RPTC simplex/duplex)
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, PacketSpec

from adn_server.application.report.payloads import _topology_peer_row
from adn_server.application.routing.helpers import (
    RF_MODE_DUPLEX,
    RF_MODE_SIMPLEX,
    SIMPLEX_VOICE_SLOT,
    derive_peer_rf_mode,
    peer_downlink_voice_slot,
    peer_is_simplex,
    peer_options_static_tg_slot,
    peer_rf_mode,
    remap_dmrd_to_peer_static_slot,
)


def _simplex_peer() -> dict:
    return {
        "SLOTS": b"4",
        "RX_FREQ": b"145500000",
        "TX_FREQ": b"145500000",
        "OPTIONS": b"TS2=7144,730444;",
    }


def _duplex_peer() -> dict:
    return {
        "SLOTS": b"3",
        "RX_FREQ": b"145625000",
        "TX_FREQ": b"145125000",
        "OPTIONS": b"TS1=7144;TS2=730444;",
    }


def test_derive_simplex_from_slots_byte() -> None:
    peer = {"SLOTS": b"4", "RX_FREQ": b"", "TX_FREQ": b""}
    assert derive_peer_rf_mode(peer) == RF_MODE_SIMPLEX
    assert peer_rf_mode(peer) == RF_MODE_SIMPLEX


def test_derive_simplex_from_matching_frequencies() -> None:
    peer = {"SLOTS": b"2", "RX_FREQ": b"145500000", "TX_FREQ": b"145500000"}
    assert derive_peer_rf_mode(peer) == RF_MODE_SIMPLEX


def test_derive_duplex_from_slots_and_split_frequencies() -> None:
    peer = _duplex_peer()
    assert derive_peer_rf_mode(peer) == RF_MODE_DUPLEX
    assert not peer_is_simplex(peer)


def test_simplex_forces_ts2_for_static_and_downlink_remap() -> None:
    peer = _simplex_peer()
    peer_rf_mode(peer)
    assert peer_options_static_tg_slot(peer, 7144) == SIMPLEX_VOICE_SLOT
    assert peer_options_static_tg_slot(peer, 730444) == SIMPLEX_VOICE_SLOT
    assert peer_downlink_voice_slot(peer, 1, 7144) == SIMPLEX_VOICE_SLOT
    burst = DeterministicScenario.voice_burst_spec(
        PacketSpec(dst_id=7144, slot=1, peer_id=730002, rf_src=730002),
        seq=1,
        dtype_vseq=1,
    ).data()
    assert burst[15] & 0x80 == 0
    remapped = remap_dmrd_to_peer_static_slot(burst, peer)
    assert remapped[15] & 0x80


def test_duplex_keeps_cross_slot_static_remap() -> None:
    peer = _duplex_peer()
    peer_rf_mode(peer)
    assert peer_downlink_voice_slot(peer, 2, 7144) == 1
    burst = DeterministicScenario.voice_burst_spec(
        PacketSpec(dst_id=7144, slot=2, peer_id=730001, rf_src=730001),
        seq=1,
        dtype_vseq=1,
    ).data()
    remapped = remap_dmrd_to_peer_static_slot(burst, peer)
    assert not (remapped[15] & 0x80)


def test_topology_peer_row_includes_rf_mode() -> None:
    peer = _simplex_peer()
    peer_rf_mode(peer)
    row = _topology_peer_row(730002, peer)
    assert row["rf_mode"] == RF_MODE_SIMPLEX
