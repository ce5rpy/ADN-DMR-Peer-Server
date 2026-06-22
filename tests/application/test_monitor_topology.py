# ADN DMR Peer Server - tests application monitor topology
#
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

"""Monitor topology parity for inject-only proxy (legacy SYSTEM-N report shape)."""

from __future__ import annotations

import time

import pytest

from adn_server.application.report.monitor_topology import (
    expand_inject_proxy_systems,
    remap_inject_proxy_voice_event,
    remap_inject_proxy_voice_events,
)
from adn_server.application.report.payloads import build_topology
from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD, HBPF_SLT_VTERM


def _peer(*, connected: bool = True, options: bytes | None = None) -> dict:
    row = {
        "CONNECTION": "YES" if connected else "NO",
        "CONNECTED": 1_700_000_000 if connected else 0,
        "IP": "203.0.113.10",
        "PORT": 62031,
        "CALLSIGN": b"CE5RPY  ",
        "RX_FREQ": b"145625000",
        "TX_FREQ": b"145625000",
    }
    if options is not None:
        row["OPTIONS"] = options
    return row


def _proxy_config(
    peers: dict[bytes, dict],
    *,
    max_peers: int = 102,
    base_port: int = 56400,
) -> dict:
    return {
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
        "SYSTEMS": {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": max_peers,
                "_REPORT_BASE_PORT": base_port,
                "PEERS": peers,
            }
        },
    }


def test_expand_inject_proxy_fans_peers_into_system_n() -> None:
    peer_a = bytes_4(730039101)
    peer_b = bytes_4(7301896)
    config = _proxy_config({peer_a: _peer(), peer_b: _peer()})
    config["SYSTEMS"]["ECHO"] = {"MODE": "MASTER", "ENABLED": True, "PEERS": {}}
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
    config = _proxy_config({peer: _peer()})
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


def test_expand_inject_clears_merged_system_static_on_virtual() -> None:
    peer = bytes_4(730039101)
    config = _proxy_config({peer: _peer(options=b"TS2=7305;")})
    config["SYSTEMS"]["SYSTEM"]["TS2_STATIC"] = "730,7305,214091"
    expanded = expand_inject_proxy_systems(config, config["SYSTEMS"], {peer: 2})
    assert expanded["SYSTEM-2"]["TS2_STATIC"] == ""
    assert expanded["SYSTEM-2"]["TS1_STATIC"] == ""


def test_expand_inject_proxy_emits_all_virtual_masters() -> None:
    peer = bytes_4(730039101)
    config = _proxy_config({peer: _peer()}, max_peers=4)
    expanded = expand_inject_proxy_systems(config, config["SYSTEMS"], {peer: 2})
    for slot in range(4):
        assert f"SYSTEM-{slot}" in expanded
        assert expanded[f"SYSTEM-{slot}"]["PORT"] == 56400 + slot
    assert list(expanded["SYSTEM-2"]["PEERS"]) == [peer]
    assert expanded["SYSTEM-0"]["PEERS"] == {}
    assert expanded["SYSTEM-1"]["PEERS"] == {}


@pytest.mark.parametrize(
    "raw,peer_specs,slot_map,expect",
    [
        pytest.param(
            "GROUP VOICE,START,RX,SYSTEM,3262598598,730039101,730039101,2,730444",
            [(730039101,)],
            {730039101: 4},
            {"startswith": "GROUP VOICE,START,RX,SYSTEM-4,"},
            id="rx_to_virtual_master",
        ),
        pytest.param(
            "GROUP VOICE,START,TX,SYSTEM,4100887026,9990,730039101,2,730444",
            [(730039101,)],
            {730039101: 4},
            {"parts": {3: "SYSTEM-4", 5: "9990"}},
            id="tx_echo_keeps_9990_for_hotspot_rx",
        ),
        pytest.param(
            "GROUP VOICE,START,TX,SYSTEM,4100887026,730039101,730039101,2,9990",
            [(730039101,)],
            {730039101: 4},
            {"parts": {3: "SYSTEM-4", 5: "9990"}},
            id="tx_echo_peer_id_in_field5_dst_9990",
        ),
        pytest.param(
            "GROUP VOICE,START,RX,SYSTEM,4100887026,73003,7300392,2,9990",
            [(730039101,)],
            {730039101: 4},
            {"parts": {3: "SYSTEM-4", 5: "730039101"}},
            id="rx_normalizes_field5_to_hotspot_radio_id",
        ),
        pytest.param(
            "GROUP VOICE,START,TX,SYSTEM,2693411696,9990,7300392,2,9990",
            [(730039101,)],
            {730039101: 4},
            {"parts": {3: "SYSTEM-4", 5: "9990"}},
            id="single_hotspot_user_prefix",
        ),
        pytest.param(
            "GROUP VOICE,START,TX,SYSTEM,2693411696,9990,7300391,2,9990",
            [(730039101,), (730039102,)],
            {730039101: 4, 730039102: 5},
            {"unchanged": True},
            id="ambiguous_user_multiple_hotspots",
        ),
        pytest.param(
            "GROUP VOICE,START,TX,SYSTEM,4100887026,9990,730039102,2,730444",
            [(730039101,), (730039102,)],
            {730039101: 4, 730039102: 5},
            {"parts": {3: "SYSTEM-5", 5: "9990"}},
            id="full_radio_id_with_sibling_hotspots",
        ),
    ],
)
def test_remap_voice_event_inject_proxy(
    raw: str,
    peer_specs: list[tuple[int, ...]],
    slot_map: dict[int, int],
    expect: dict,
) -> None:
    peers = {bytes_4(rid): _peer() for spec in peer_specs for rid in spec}
    peer_slots = {bytes_4(rid): slot_map[rid] for spec in peer_specs for rid in spec}
    config = _proxy_config(peers)
    remapped = remap_inject_proxy_voice_event(
        raw, config, config["SYSTEMS"], peer_slots
    )
    if expect.get("unchanged"):
        assert remapped == raw
        return
    if prefix := expect.get("startswith"):
        assert remapped.startswith(prefix)
        return
    parts = remapped.split(",")
    for idx, value in expect.get("parts", {}).items():
        assert parts[idx] == value


def test_local_hotspot_rx_fans_out_tx_only_to_peers_with_matching_tg() -> None:
    """REPEAT companion TX only for hotspots that have the TG in OPTIONS."""
    peers = {
        bytes_4(7301795): _peer(options=b"TS2=730444;"),
        bytes_4(7300444): _peer(options=b"TS2=730444;"),
        bytes_4(730039101): _peer(options=b"TS2=91;"),
    }
    config = _proxy_config(peers)
    peer_slots = {
        bytes_4(7301795): 1,
        bytes_4(7300444): 3,
        bytes_4(730039101): 4,
    }
    raw = "GROUP VOICE,START,RX,SYSTEM,3262598598,7301795,7301795,2,730444"
    events = remap_inject_proxy_voice_events(
        raw, config, config["SYSTEMS"], peer_slots
    )
    assert len(events) == 2
    by_system = {ev.split(",")[3]: ev for ev in events}
    assert "SYSTEM-1" in by_system
    assert by_system["SYSTEM-1"].startswith("GROUP VOICE,START,RX,SYSTEM-1,")
    assert "SYSTEM-3" in by_system
    assert by_system["SYSTEM-3"].startswith("GROUP VOICE,START,TX,SYSTEM-3,")
    assert "SYSTEM-4" not in by_system


def test_local_hotspot_rx_companion_tx_uses_receiver_options_slot() -> None:
    """HS2 TX slot 2 / TG 7144 → HS1 with TS1=7144 gets BRDG field 7 = 1 (monitor TE)."""
    hs1 = bytes_4(730001)
    hs2 = bytes_4(730002)
    peers = {
        hs1: _peer(options=b"TS1=7144;TS2=714,71442;"),
        hs2: _peer(options=b"TS2=7144;"),
    }
    peers[hs1]["TX_FREQ"] = b"145825000"
    config = _proxy_config(peers)
    peer_slots = {hs1: 0, hs2: 1}
    raw = "GROUP VOICE,START,RX,SYSTEM,3262598598,730002,730002,2,7144"
    events = remap_inject_proxy_voice_events(
        raw, config, config["SYSTEMS"], peer_slots
    )
    tx_events = [e for e in events if e.split(",")[2] == "TX"]
    assert len(tx_events) == 1
    parts = tx_events[0].split(",")
    assert parts[3] == "SYSTEM-0"
    assert int(parts[7]) == 1


def test_obp_tx_single_hotspot_remaps_dynamic_tg_not_in_static() -> None:
    """One HS online: downlink/monitor must remap TX even when TG is UA-only (not in OPTIONS)."""
    peer = bytes_4(730039101)
    peers = {peer: _peer(options=b"TS2=730,7305;")}
    config = _proxy_config(peers)
    peer_slots = {peer: 2}
    raw = "GROUP VOICE,START,TX,SYSTEM,4100887026,73010,7000002,2,730444"
    bridges = {
        "730444": [
            {
                "SYSTEM": "SYSTEM",
                "TS": 2,
                "TGID": 730444,
                "ACTIVE": True,
                "TO_TYPE": "ON",
            }
        ],
    }
    events = remap_inject_proxy_voice_events(
        raw, config, config["SYSTEMS"], peer_slots, bridges
    )
    assert len(events) == 1
    assert events[0].startswith("GROUP VOICE,START,TX,SYSTEM-2,")


def test_obp_bridge_tx_fans_out_only_to_peers_with_matching_static_tg() -> None:
    """OBP downlink TX must not light hotspots without the TG in OPTIONS."""
    peers = {
        bytes_4(7300444): _peer(options=b"TS2=730444;"),
        bytes_4(7301795): _peer(options=b"TS2=730444;"),
        bytes_4(730039101): _peer(options=b"TS2=91;"),
    }
    config = _proxy_config(peers)
    peer_slots = {bytes_4(7300444): 3, bytes_4(7301795): 1, bytes_4(730039101): 4}
    raw = "GROUP VOICE,START,TX,SYSTEM,4100887026,73010,7000002,2,730444"
    bridges = {
        "730444": [
            {
                "SYSTEM": "SYSTEM",
                "TS": 2,
                "ACTIVE": True,
                "TO_TYPE": "ON",
            }
        ],
    }
    events = remap_inject_proxy_voice_events(
        raw, config, config["SYSTEMS"], peer_slots, bridges
    )
    systems = {ev.split(",")[3] for ev in events}
    assert systems == {"SYSTEM-1", "SYSTEM-3"}
    assert all(ev.split(",")[5] == "73010" for ev in events)


def test_remap_voice_event_passes_through_non_proxy_systems() -> None:
    raw = "GROUP VOICE,START,RX,ECHO,1,9990,730039101,2,9990"
    assert remap_inject_proxy_voice_event(raw, {}, {}) == raw


def test_non_proxy_systems_pass_through_unchanged() -> None:
    systems = {
        "ECHO": {"MODE": "MASTER", "ENABLED": True, "PEERS": {}},
    }
    assert expand_inject_proxy_systems({"PROXY": {"TARGET_SYSTEM": "SYSTEM"}}, systems) is systems


def test_companion_tx_suppressed_when_receiver_slot_busy_on_other_tg() -> None:
    """HS1 TX on TG 7144 must not get companion TX for another peer's TG on the same slot."""
    hs1 = bytes_4(730001)
    hs2 = bytes_4(730002)
    peers = {
        hs1: _peer(options=b"TS2=7144,730444;"),
        hs2: _peer(options=b"TS2=730444;"),
    }
    config = _proxy_config(peers)
    peer_slots = {hs1: 0, hs2: 1}
    master_status = {
        2: {
            "RX_TYPE": HBPF_SLT_VHEAD,
            "TX_TYPE": HBPF_SLT_VTERM,
            "RX_PEER": hs1,
            "RX_TGID": bytes_3(7144),
            "RX_STREAM_ID": bytes_4(0x11111111),
            "RX_TIME": time.time(),
            "TX_TIME": 0.0,
        }
    }
    raw = "GROUP VOICE,START,RX,SYSTEM,222,730002,730002,2,730444"
    events = remap_inject_proxy_voice_events(
        raw, config, config["SYSTEMS"], peer_slots, master_status=master_status
    )
    assert len(events) == 1
    assert events[0].split(",")[3] == "SYSTEM-1"
    assert events[0].split(",")[2] == "RX"


def test_obp_tx_fanout_suppressed_when_peer_slot_busy_on_other_tg() -> None:
    """OBP downlink TX must not light a hotspot already active on another TG (same slot)."""
    hs1 = bytes_4(7300444)
    hs2 = bytes_4(7301795)
    peers = {
        hs1: _peer(options=b"TS2=7144,730444;"),
        hs2: _peer(options=b"TS2=730444;"),
    }
    config = _proxy_config(peers)
    peer_slots = {hs1: 3, hs2: 1}
    master_status = {
        2: {
            "RX_TYPE": HBPF_SLT_VHEAD,
            "TX_TYPE": HBPF_SLT_VTERM,
            "RX_PEER": hs1,
            "RX_TGID": bytes_3(7144),
            "RX_STREAM_ID": bytes_4(0x11111111),
            "RX_TIME": time.time(),
            "TX_TIME": 0.0,
        }
    }
    raw = "GROUP VOICE,START,TX,SYSTEM,4100887026,73010,7000002,2,730444"
    bridges = {
        "730444": [
            {
                "SYSTEM": "SYSTEM",
                "TS": 2,
                "TGID": 730444,
                "ACTIVE": True,
                "TO_TYPE": "ON",
            }
        ],
    }
    events = remap_inject_proxy_voice_events(
        raw,
        config,
        config["SYSTEMS"],
        peer_slots,
        bridges,
        master_status=master_status,
    )
    systems = {ev.split(",")[3] for ev in events}
    assert systems == {"SYSTEM-1"}
