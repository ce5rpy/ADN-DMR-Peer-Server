"""Monitor topology parity for inject-only proxy (legacy SYSTEM-N report shape)."""

from __future__ import annotations

from adn_server.application.report.monitor_topology import (
    expand_inject_proxy_systems,
    remap_inject_proxy_voice_event,
)
from adn_server.application.report.payloads import build_topology
from adn_server.domain.value_objects import bytes_4


def _peer(*, connected: bool = True) -> dict:
    return {
        "CONNECTION": "YES" if connected else "NO",
        "CONNECTED": 1_700_000_000 if connected else 0,
        "IP": "203.0.113.10",
        "PORT": 62031,
        "CALLSIGN": b"CE5RPY  ",
        "RX_FREQ": b"145625000",
        "TX_FREQ": b"145625000",
    }


def test_expand_inject_proxy_fans_peers_into_system_n() -> None:
    peer_a = bytes_4(730039101)
    peer_b = bytes_4(7301896)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "_REPORT_BASE_PORT": 56400,
                "PEERS": {
                    peer_a: _peer(),
                    peer_b: _peer(),
                },
            },
            "ECHO": {"MODE": "MASTER", "ENABLED": True, "PEERS": {}},
        },
    }
    expanded = expand_inject_proxy_systems(
        config,
        config["SYSTEMS"],
        {peer_a: 2, peer_b: 66},
    )
    assert "SYSTEM" not in expanded
    assert expanded["SYSTEM-2"]["PORT"] == 56402
    assert expanded["SYSTEM-66"]["PORT"] == 56466
    assert list(expanded["SYSTEM-2"]["PEERS"]) == [peer_a]
    assert list(expanded["SYSTEM-66"]["PEERS"]) == [peer_b]
    assert "ECHO" in expanded


def test_build_topology_after_expand_matches_monitor_shape() -> None:
    peer = bytes_4(730039101)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "_REPORT_BASE_PORT": 56400,
                "PEERS": {peer: _peer()},
            }
        },
    }
    expanded = expand_inject_proxy_systems(config, config["SYSTEMS"], {peer: 2})
    doc = build_topology(expanded, seq=1)
    names = {system["name"] for system in doc["systems"]}
    assert "SYSTEM" not in names
    assert "SYSTEM-2" in names
    system = next(item for item in doc["systems"] if item["name"] == "SYSTEM-2")
    assert system["port"] == 56402
    assert len(system["peers"]) == 1
    row = system["peers"][0]
    assert row["id"] == 730039101
    assert row["connected"] is True
    assert row["ip"] == "203.0.113.10"
    assert row["callsign"] == "CE5RPY"


def test_expand_inject_proxy_emits_all_virtual_masters() -> None:
    peer = bytes_4(730039101)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 4,
                "_REPORT_BASE_PORT": 56400,
                "PEERS": {peer: _peer()},
            }
        },
    }
    expanded = expand_inject_proxy_systems(config, config["SYSTEMS"], {peer: 2})
    for slot in range(4):
        assert f"SYSTEM-{slot}" in expanded
        assert expanded[f"SYSTEM-{slot}"]["PORT"] == 56400 + slot
    assert list(expanded["SYSTEM-2"]["PEERS"]) == [peer]
    assert expanded["SYSTEM-0"]["PEERS"] == {}
    assert expanded["SYSTEM-1"]["PEERS"] == {}


def test_remap_voice_event_system_to_virtual_master() -> None:
    peer = bytes_4(730039101)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "PEERS": {peer: _peer()},
            }
        },
    }
    raw = "GROUP VOICE,START,RX,SYSTEM,3262598598,730039101,730039101,2,730444"
    remapped = remap_inject_proxy_voice_event(
        raw, config, config["SYSTEMS"], {peer: 4}
    )
    assert remapped.startswith("GROUP VOICE,START,RX,SYSTEM-4,")


def test_remap_voice_event_tx_keeps_echo_peer_id_for_hotspot_rx_display() -> None:
    """TX echo→hotspot: field 5 stays 9990 so hotspot chip is TX/green while receiving."""
    peer = bytes_4(730039101)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "PEERS": {peer: _peer()},
            }
        },
    }
    raw = "GROUP VOICE,START,TX,SYSTEM,4100887026,9990,730039101,2,730444"
    remapped = remap_inject_proxy_voice_event(
        raw, config, config["SYSTEMS"], {peer: 4}
    )
    parts = remapped.split(",")
    assert parts[3] == "SYSTEM-4"
    assert parts[5] == "9990"


def test_remap_voice_event_rx_normalizes_field5_to_hotspot_radio_id() -> None:
    peer = bytes_4(730039101)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "PEERS": {peer: _peer()},
            }
        },
    }
    raw = "GROUP VOICE,START,RX,SYSTEM,4100887026,73003,7300392,2,9990"
    remapped = remap_inject_proxy_voice_event(
        raw, config, config["SYSTEMS"], {peer: 4}
    )
    parts = remapped.split(",")
    assert parts[3] == "SYSTEM-4"
    assert parts[5] == "730039101"


def test_remap_voice_event_matches_user_prefix_when_single_hotspot_online() -> None:
    """User 7300391 with only HS1 online: legacy short subscriber id can resolve."""
    peer = bytes_4(730039101)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "PEERS": {peer: _peer()},
            }
        },
    }
    raw = "GROUP VOICE,START,TX,SYSTEM,2693411696,9990,7300392,2,9990"
    remapped = remap_inject_proxy_voice_event(
        raw, config, config["SYSTEMS"], {peer: 4}
    )
    parts = remapped.split(",")
    assert parts[3] == "SYSTEM-4"
    assert parts[5] == "9990"


def test_remap_voice_event_skips_ambiguous_user_with_multiple_hotspots() -> None:
    """User 7300391 + HS1/HS2 online: do not pick the wrong radio from rf_src alone."""
    hs1 = bytes_4(730039101)
    hs2 = bytes_4(730039102)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "PEERS": {hs1: _peer(), hs2: _peer()},
            }
        },
    }
    raw = "GROUP VOICE,START,TX,SYSTEM,2693411696,9990,7300391,2,9990"
    remapped = remap_inject_proxy_voice_event(
        raw, config, config["SYSTEMS"], {hs1: 4, hs2: 5}
    )
    assert remapped == raw


def test_remap_voice_event_resolves_full_radio_id_with_sibling_hotspots_online() -> None:
    """Full radio id in rf_src still maps correctly when sibling HS are connected."""
    hs1 = bytes_4(730039101)
    hs2 = bytes_4(730039102)
    config = {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "PEERS": {hs1: _peer(), hs2: _peer()},
            }
        },
    }
    raw = "GROUP VOICE,START,TX,SYSTEM,4100887026,9990,730039102,2,730444"
    remapped = remap_inject_proxy_voice_event(
        raw, config, config["SYSTEMS"], {hs1: 4, hs2: 5}
    )
    parts = remapped.split(",")
    assert parts[3] == "SYSTEM-5"
    assert parts[5] == "9990"


def test_remap_voice_event_passes_through_non_proxy_systems() -> None:
    raw = "GROUP VOICE,START,RX,ECHO,1,9990,730039101,2,9990"
    assert remap_inject_proxy_voice_event(raw, {}, {}) == raw


def test_non_proxy_systems_pass_through_unchanged() -> None:
    systems = {
        "ECHO": {"MODE": "MASTER", "ENABLED": True, "PEERS": {}},
    }
    assert expand_inject_proxy_systems({"PROXY": {"TARGET_SYSTEM": "SYSTEM"}}, systems) is systems
