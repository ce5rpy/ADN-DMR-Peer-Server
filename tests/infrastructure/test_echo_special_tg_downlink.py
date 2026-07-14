# ADN DMR Peer Server - echo / special TG downlink filter non-regression
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
# Regression test: TG 9990 (echo) and special TGs 9990-9999 must only be
# delivered to the exact peer that originated the call, never replicated
# to other hotspots of the same user (same DMR ID base).

from __future__ import annotations

from adn_server.application.routing.helpers import synthetic_group_dmrd_route_packet
from adn_server.domain import bytes_3, bytes_4
from adn_server.infrastructure.config_normalizer import ensure_system_runtime_config
from adn_server.infrastructure.twisted_adapters.udp_hbp import HBPProtocol


def _master_config() -> dict:
    config = {
        "GLOBAL": {"USE_ACL": False},
        "SYSTEMS": {
            "TEST": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 8,
                "GROUP_HANGTIME": 0,
            }
        },
    }
    ensure_system_runtime_config(config)
    return config


def _make_echo_packet(rf_src_base: int, tgid: int = 9990) -> bytes:
    """Build a DMRD group packet for TG 9990 with a given rf_src (3-byte base)."""
    pkt = synthetic_group_dmrd_route_packet(2, tgid)
    return pkt[:5] + bytes_3(rf_src_base) + pkt[8:]


def test_echo_9990_only_to_originating_peer() -> None:
    """Echo playback must deliver ONLY to the RX_PEER that originated the call."""
    config = _master_config()
    proto = HBPProtocol("TEST", config)
    peer_a = bytes_4(730039101)
    peer_b = bytes_4(730039210)
    proto._peers = {
        peer_a: {"CONNECTION": "YES", "OPTIONS": b"", "SOCKADDR": ("127.0.0.1", 62031)},
        peer_b: {"CONNECTION": "YES", "OPTIONS": b"", "SOCKADDR": ("127.0.0.1", 62040)},
    }
    # Simulate: peer_a transmitted to TG 9990 on slot 2 (RX_PEER set by dmrd_received).
    proto.STATUS[2] = {
        "RX_PEER": peer_a,
        "RX_TGID": bytes_3(9990),
        "RX_STREAM_ID": b"\x00\x00\x00\x01",
    }
    rf_src_base = 7300392  # both peers share this base ID (same user)
    echo_pkt = _make_echo_packet(rf_src_base, 9990)
    assert proto._peer_should_receive_dmrd(peer_a, echo_pkt)
    assert not proto._peer_should_receive_dmrd(peer_b, echo_pkt)


def test_echo_9990_no_fuzzy_match_when_no_rx_peer() -> None:
    """When RX_PEER is not set, echo must NOT use fuzzy rf_src matching.

    With multiple peers connected, no peer should receive the echo if the
    originating RX_PEER is unknown (single-peer fallback is the only exception).
    """
    config = _master_config()
    proto = HBPProtocol("TEST", config)
    peer_a = bytes_4(730039101)
    peer_b = bytes_4(730039210)
    proto._peers = {
        peer_a: {"CONNECTION": "YES", "OPTIONS": b"", "SOCKADDR": ("127.0.0.1", 62031)},
        peer_b: {"CONNECTION": "YES", "OPTIONS": b"", "SOCKADDR": ("127.0.0.1", 62040)},
    }
    # RX_PEER not set (stale / different TG on slot)
    proto.STATUS[2] = {
        "RX_PEER": b"\x00\x00\x00\x00",
        "RX_TGID": bytes_3(0),
        "RX_STREAM_ID": b"\x00\x00\x00\x00",
    }
    rf_src_base = 7300392
    echo_pkt = _make_echo_packet(rf_src_base, 9990)
    assert not proto._peer_should_receive_dmrd(peer_a, echo_pkt)
    assert not proto._peer_should_receive_dmrd(peer_b, echo_pkt)


def test_echo_9990_single_peer_fallback() -> None:
    """When only one peer is connected, echo is delivered to it (legacy parity)."""
    config = _master_config()
    proto = HBPProtocol("TEST", config)
    peer_a = bytes_4(730039101)
    proto._peers = {
        peer_a: {"CONNECTION": "YES", "OPTIONS": b"", "SOCKADDR": ("127.0.0.1", 62031)},
    }
    proto.STATUS[2] = {
        "RX_PEER": b"\x00\x00\x00\x00",
        "RX_TGID": bytes_3(0),
        "RX_STREAM_ID": b"\x00\x00\x00\x00",
    }
    rf_src_base = 7300392
    echo_pkt = _make_echo_packet(rf_src_base, 9990)
    assert proto._peer_should_receive_dmrd(peer_a, echo_pkt)


def test_special_tg_9991_same_isolation() -> None:
    """All special TGs 9990-9999 share the same point-to-point isolation."""
    config = _master_config()
    proto = HBPProtocol("TEST", config)
    peer_a = bytes_4(730039101)
    peer_b = bytes_4(730039210)
    proto._peers = {
        peer_a: {"CONNECTION": "YES", "OPTIONS": b"", "SOCKADDR": ("127.0.0.1", 62031)},
        peer_b: {"CONNECTION": "YES", "OPTIONS": b"", "SOCKADDR": ("127.0.0.1", 62040)},
    }
    proto.STATUS[2] = {
        "RX_PEER": peer_b,
        "RX_TGID": bytes_3(9991),
        "RX_STREAM_ID": b"\x00\x00\x00\x01",
    }
    rf_src_base = 7300392
    pkt = _make_echo_packet(rf_src_base, 9991)
    assert proto._peer_should_receive_dmrd(peer_b, pkt)
    assert not proto._peer_should_receive_dmrd(peer_a, pkt)
