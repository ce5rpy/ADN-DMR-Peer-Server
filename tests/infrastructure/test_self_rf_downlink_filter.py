# ADN DMR Peer Server - self rf_src downlink filter
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations

from adn_server.application.routing.downlink import touch_peer_voice_slot
from adn_server.application.routing.helpers import peer_matches_rf_source, synthetic_group_dmrd_route_packet
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


def test_group_downlink_blocked_when_self_rf_during_ingress_tx() -> None:
    """Base rf_src echo must not downlink to a hotspot that is still transmitting."""
    config = _master_config()
    proto = HBPProtocol("TEST", config)
    peer_id = bytes_4(730039264)
    proto._peers = {
        peer_id: {
            "CONNECTION": "YES",
            "OPTIONS": b"TS2=730502;",
            "SOCKADDR": ("127.0.0.1", 62031),
        },
    }
    ctx = proto._downlink_ctx()
    touch_peer_voice_slot(
        ctx,
        peer_id,
        2,
        bytes_4(0x11111111),
        bytes_3(730502),
        ingress=True,
    )
    base_rf = bytes_3(730039264 // 100)
    pkt = synthetic_group_dmrd_route_packet(2, 730502)
    pkt = pkt[:5] + base_rf + pkt[8:]
    assert peer_matches_rf_source(peer_id, base_rf, proto._peers)
    assert not proto._peer_should_receive_dmrd(peer_id, pkt)


def test_group_downlink_allowed_for_shared_base_rf_when_not_tx() -> None:
    """Lab peers sharing rf_src base id may RX each other when not transmitting."""
    config = _master_config()
    proto = HBPProtocol("TEST", config)
    peer_id = bytes_4(730039264)
    other = bytes_4(730039265)
    proto._peers = {
        peer_id: {
            "CONNECTION": "YES",
            "OPTIONS": b"TS2=730502;",
            "SOCKADDR": ("127.0.0.1", 62031),
        },
        other: {
            "CONNECTION": "YES",
            "OPTIONS": b"TS2=730502;",
            "SOCKADDR": ("127.0.0.1", 62032),
        },
    }
    foreign_rf = bytes_3(730039265 // 100)
    pkt = synthetic_group_dmrd_route_packet(2, 730502)
    pkt = pkt[:5] + foreign_rf + pkt[8:]
    assert proto._peer_should_receive_dmrd(peer_id, pkt)
