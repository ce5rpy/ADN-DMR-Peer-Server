"""BRDG_EVENT peer_id resolution for RX legs (hotspot transmitting)."""

from __future__ import annotations

from adn_server.application.bridge.helpers import resolve_voice_peer_id
from adn_server.domain.value_objects import bytes_3, bytes_4


def test_resolve_voice_peer_uses_rf_src_when_field5_is_network_id() -> None:
    hotspot = bytes_4(730039101)
    systems = {
        "SYSTEM": {
            "PEERS": {
                hotspot: {"CONNECTION": "YES"},
            }
        }
    }
    network_peer = bytes_4(73003)
    resolved = resolve_voice_peer_id(
        network_peer,
        bytes_3(730039101),
        "SYSTEM",
        systems,
    )
    assert resolved == hotspot


def test_resolve_voice_peer_keeps_known_hotspot_id() -> None:
    hotspot = bytes_4(730039102)
    systems = {"SYSTEM": {"PEERS": {hotspot: {"CONNECTION": "YES"}}}}
    resolved = resolve_voice_peer_id(
        hotspot,
        bytes_3(730039102),
        "SYSTEM",
        systems,
    )
    assert resolved == hotspot


def test_resolve_voice_peer_resolves_network_prefix_for_single_hotspot() -> None:
    hotspot = bytes_4(730039101)
    systems = {"SYSTEM": {"PEERS": {hotspot: {"CONNECTION": "YES"}}}}
    resolved = resolve_voice_peer_id(
        bytes_4(73003),
        bytes_3(7300392),
        "SYSTEM",
        systems,
    )
    assert resolved == hotspot
