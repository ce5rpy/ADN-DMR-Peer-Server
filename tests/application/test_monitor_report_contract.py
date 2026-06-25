# ADN DMR Peer Server - tests application monitor report contract
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

"""Report ↔ monitor contract tests (would have caught the 2026-06 production outage).

Unit tests on expansion/topology alone are insufficient: adn-monitor deletes masters
not present in CONFIG and only adds peers under masters that already exist in CTABLE.
These tests model that behaviour and assert the server report snapshot is safe.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from tests.support.monitor_ctable_sim import (
    apply_config_to_ctable,
    apply_slim_dashboard_state,
    config_from_systems,
    count_master_peers,
    count_masters,
    ctable_with_virtual_masters,
    empty_ctable,
    sparse_expand_buggy,
    update_ctable_from_config,
)

from adn_server.application.report.dashboard_state import build_dashboard_state
from adn_server.application.report.monitor_topology import (
    expand_inject_proxy_systems,
    remap_inject_proxy_voice_event,
)
from adn_server.application.report.payloads import build_topology
from adn_server.domain.value_objects import bytes_4
from adn_server.infrastructure.twisted_adapters.report.opcodes import REPORT_OPCODES
from adn_server.infrastructure.twisted_adapters.report.wire import ReportWire
from adn_server.infrastructure.twisted_adapters.report_server import ReportServerFactory

MAX_PEERS = 102
BASE_PORT = 56400


def _peer(peer_id: int, *, slot: int | None = None) -> dict[str, Any]:
    return {
        "CONNECTION": "YES",
        "CONNECTED": 1_700_000_000,
        "IP": "203.0.113.10",
        "PORT": 62031,
        "CALLSIGN": b"CE5RPY  ",
    }


def _inject_runtime_systems(peer_specs: list[tuple[int, int]]) -> dict[str, Any]:
    """Runtime SYSTEM dict (single inject target) with peers keyed by radio ID."""
    peers = {bytes_4(pid): _peer(pid) for pid, _slot in peer_specs}
    return {
        "SYSTEM": {
            "MODE": "MASTER",
            "ENABLED": True,
            "MAX_PEERS": MAX_PEERS,
            "_REPORT_BASE_PORT": BASE_PORT,
            "PEERS": peers,
        },
        "ECHO": {"MODE": "MASTER", "ENABLED": True, "PEERS": {}},
        "D-APRS-0": {"MODE": "MASTER", "ENABLED": True, "PEERS": {}},
        "OBP-CL": {
            "MODE": "OPENBRIDGE",
            "ENABLED": True,
            "NETWORK_ID": bytes_4(73010),
            "PEERS": {},
        },
    }


def _proxy_config() -> dict[str, Any]:
    return {
        "REPORTS": {"REPORT": True, "REPORT_CLIENTS": ["*"]},
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
    }


def _peer_slots(peer_specs: list[tuple[int, int]]) -> dict[bytes, int]:
    return {bytes_4(pid): slot for pid, slot in peer_specs}


def _production_snapshot(
    peer_specs: list[tuple[int, int]],
) -> dict[str, Any]:
    systems = _inject_runtime_systems(peer_specs)
    return expand_inject_proxy_systems(
        _proxy_config(),
        systems,
        _peer_slots(peer_specs),
    )


def _system_n_names(config: dict[str, Any], *, target: str = "SYSTEM") -> set[str]:
    return {name for name in config if name.startswith(f"{target}-")}


def test_sparse_expansion_fails_monitor_master_preservation_contract() -> None:
    """Regression: sparse SYSTEM-N-only snapshots delete 99+ masters on monitor update."""
    peer_specs = [(730039101, 4), (7301896, 6), (7301795, 1)]
    runtime = _inject_runtime_systems(peer_specs)
    slots = _peer_slots(peer_specs)
    sparse = sparse_expand_buggy(_proxy_config(), runtime, slots)

    ctable = ctable_with_virtual_masters(max_slots=MAX_PEERS)
    before = count_masters(ctable)
    update_ctable_from_config(sparse, ctable)

    assert before == MAX_PEERS + 2  # SYSTEM-0..101 + ECHO + D-APRS-0
    assert count_masters(ctable) == 2 + len(_system_n_names(sparse))
    assert count_masters(ctable) < 10


def test_full_expansion_passes_monitor_master_preservation_contract() -> None:
    """Healthy monitor CTABLE must survive every server report push."""
    peer_specs = [(730039101, 4), (7301896, 6), (7301795, 1)]
    full = _production_snapshot(peer_specs)

    ctable = ctable_with_virtual_masters(max_slots=MAX_PEERS)
    before = count_masters(ctable)
    update_ctable_from_config(full, ctable)

    assert count_masters(ctable) == before
    assert len(_system_n_names(full)) == MAX_PEERS


def test_full_expansion_surfaces_all_hotspot_peers_on_fresh_monitor() -> None:
    """First connect (empty CTABLE): all connected peers must appear under SYSTEM-N."""
    peer_specs = [
        (730050, 0),
        (7301795, 1),
        (7303246, 2),
        (7300444, 3),
        (730039101, 4),
        (730266501, 5),
        (7301896, 6),
    ]
    full = _production_snapshot(peer_specs)
    ctable = empty_ctable()
    apply_config_to_ctable(full, ctable)

    assert count_masters(ctable) == MAX_PEERS + 2
    assert count_master_peers(ctable) == len(peer_specs)


def test_legacy_boot_sequence_echo_then_full_loses_hotspot_peers() -> None:
    """2026-06 prod outage: first snapshot ECHO only, then full Chile proxy — legacy update drops peers."""
    peer_specs = [
        (7300444, 1),
        (7301795, 3),
        (730197002, 0),
        (730179501, 2),
        (7303246, 4),
        (730039101, 5),
        (7301896, 6),
    ]
    full_systems = _production_snapshot(peer_specs)
    full_systems["ECHO"] = {
        "MODE": "MASTER",
        "ENABLED": True,
        "PEERS": {bytes_4(9990): _peer(9990)},
    }
    full_config = config_from_systems(full_systems)
    echo_only = config_from_systems(
        {
            "ECHO": {
                "MODE": "MASTER",
                "ENABLED": True,
                "PEERS": {bytes_4(9990): _peer(9990)},
            }
        }
    )

    ctable = empty_ctable()
    apply_config_to_ctable(echo_only, ctable)
    assert count_masters(ctable) == 1
    apply_config_to_ctable(full_config, ctable)

    assert count_masters(ctable) == 1
    assert count_master_peers(ctable) == 1


def test_slim_boot_sequence_echo_then_full_keeps_all_chile_hotspot_peers() -> None:
    """D-25: each dashboard_state is a full snapshot — boot sequence must surface every SYSTEM-N peer."""
    peer_specs = [
        (7300444, 1),
        (7301795, 3),
        (730197002, 0),
        (730179501, 2),
        (7303246, 4),
        (730039101, 5),
        (7301896, 6),
    ]
    full_systems = _production_snapshot(peer_specs)
    full_systems["ECHO"] = {
        "MODE": "MASTER",
        "ENABLED": True,
        "PEERS": {bytes_4(9990): _peer(9990)},
    }
    full_config = config_from_systems(full_systems)
    echo_only = config_from_systems(
        {
            "ECHO": {
                "MODE": "MASTER",
                "ENABLED": True,
                "PEERS": {bytes_4(9990): _peer(9990)},
            },
            "OBP-CL": {
                "MODE": "OPENBRIDGE",
                "ENABLED": True,
                "NETWORK_ID": bytes_4(73010),
                "PEERS": {},
            },
        }
    )

    ctable = empty_ctable()
    apply_slim_dashboard_state(echo_only, ctable)
    apply_slim_dashboard_state(full_config, ctable)

    assert count_masters(ctable) == len(peer_specs) + 1
    assert count_master_peers(ctable) == len(peer_specs) + 1


def test_wire_dashboard_state_boot_sequence_matches_slim_apply() -> None:
    """End-to-end: server STATE_SND payload → CONFIG → slim CTABLE (prod reconnect path)."""
    peer_specs = [(730039101, 5), (7301896, 6)]
    systems = _production_snapshot(peer_specs)
    systems["ECHO"] = {
        "MODE": "MASTER",
        "ENABLED": True,
        "PEERS": {bytes_4(9990): _peer(9990)},
    }
    echo_doc = build_dashboard_state(
        {
            "ECHO": {
                "MODE": "MASTER",
                "ENABLED": True,
                "PEERS": {bytes_4(9990): _peer(9990)},
            },
            "OBP-CL": {
                "MODE": "OPENBRIDGE",
                "ENABLED": True,
                "NETWORK_ID": bytes_4(73010),
                "PEERS": {},
            },
        },
        ts=1.0,
    )
    full_doc = build_dashboard_state(systems, ts=2.0)

    ctable = empty_ctable()
    apply_slim_dashboard_state(config_from_systems(_doc_to_runtime(echo_doc)), ctable)
    apply_slim_dashboard_state(config_from_systems(_doc_to_runtime(full_doc)), ctable)

    assert count_master_peers(ctable) == len(peer_specs) + 1
    assert 730039101 in ctable["MASTERS"]["SYSTEM-5"]["PEERS"]
    assert 7301896 in ctable["MASTERS"]["SYSTEM-6"]["PEERS"]


def _doc_to_runtime(doc: dict[str, Any]) -> dict[str, Any]:
    """Minimal runtime SYSTEMS from dashboard_state.ctable (for build_dashboard_state round-trip)."""
    out: dict[str, Any] = {}
    for name, master in (doc.get("ctable", {}).get("MASTERS") or {}).items():
        peers = {}
        for pid, row in (master.get("peers") or {}).items():
            peers[bytes_4(int(pid))] = {
                "CONNECTION": "YES",
                "CONNECTED": row.get("connected_at", 1),
            }
        out[name] = {"MODE": "MASTER", "ENABLED": True, "PEERS": peers}
    for name in doc.get("ctable", {}).get("OPENBRIDGES") or {}:
        out[name] = {"MODE": "OPENBRIDGE", "ENABLED": True, "PEERS": {}}
    return out


def test_truncated_monitor_ctable_cannot_show_system_n_peers() -> None:
    """Characterization: legacy update path never creates SYSTEM-N rows (pre-D-25 monitor bug)."""
    peer_specs = [(730039101, 4), (7301896, 6)]
    full = _production_snapshot(peer_specs)
    damaged = empty_ctable()
    damaged["MASTERS"] = {
        "ECHO": {"PEERS": {}},
        "D-APRS-0": {"PEERS": {}},
        "D-APRS-1": {"PEERS": {}},
    }
    damaged["OPENBRIDGES"] = {"OBP-CL": {"STREAMS": {}}}

    update_ctable_from_config(full, damaged)

    assert count_masters(damaged) == 2
    assert count_master_peers(damaged) == 0
    assert "SYSTEM-4" not in damaged["MASTERS"]
    assert "SYSTEM-6" not in damaged["MASTERS"]
    assert full["SYSTEM-4"]["PEERS"]
    assert full["SYSTEM-6"]["PEERS"]


def test_report_wire_emits_dashboard_state_only() -> None:
    peer_specs = [(730039101, 4)]
    snapshot = _production_snapshot(peer_specs)
    frames = ReportWire().state_frames(snapshot, force=True)

    assert len(frames) == 1
    assert frames[0][:1] == REPORT_OPCODES["STATE_SND"]
    doc = json.loads(frames[0][1:].decode())
    assert doc["type"] == "dashboard_state"
    assert "SYSTEM-4" in doc["ctable"]["MASTERS"]
    assert len(_system_n_names(snapshot)) == MAX_PEERS


def test_report_wire_skips_unchanged_dashboard_state() -> None:
    peer_specs = [(730039101, 4)]
    snapshot = _production_snapshot(peer_specs)
    wire = ReportWire()
    assert len(wire.state_frames(snapshot, force=True)) == 1
    assert wire.state_frames(snapshot, force=False) == ()


def test_report_wire_emits_when_runtime_peer_options_change() -> None:
    """RPTO / MySQL inject must push STATE_SND so monitor chips update without reload."""
    peer_specs = [(730039101, 4)]
    systems = _inject_runtime_systems(peer_specs)
    proxy_cfg = _proxy_config()
    slots = _peer_slots(peer_specs)
    wire = ReportWire()
    expanded = expand_inject_proxy_systems(proxy_cfg, systems, slots)
    wire.state_frames(expanded, force=True)
    assert wire.state_frames(expanded, force=False) == ()

    systems["SYSTEM"]["PEERS"][bytes_4(730039101)]["OPTIONS"] = b"TS2=730444,7305;SINGLE=1;"
    expanded2 = expand_inject_proxy_systems(proxy_cfg, systems, slots)
    frames = wire.state_frames(expanded2, force=False)
    assert len(frames) == 1
    doc = json.loads(frames[0][1:].decode())
    peer_row = doc["ctable"]["MASTERS"]["SYSTEM-4"]["peers"]["730039101"]
    assert peer_row["options"] == "TS2=730444,7305;SINGLE=1;"
    assert peer_row["ts2_static"] == ["730444", "7305"]


def test_report_wire_bridge_frames_emits_routing_table() -> None:
    bridges = {
        "52090": [
            {
                "SYSTEM": "SYSTEM-0",
                "ACTIVE": True,
                "TS": 2,
                "TGID": 52090,
                "TO_TYPE": "ON",
                "TIMER": 1000.0,
            },
        ]
    }
    frames = ReportWire().bridge_frames(bridges, full_snapshot=True)
    assert len(frames) == 1
    assert frames[0][:1] == REPORT_OPCODES["ROUTING_TABLE_SND"]
    doc = json.loads(frames[0][1:].decode())
    assert doc["type"] == "routing_table"
    assert doc["routes"][0]["relay_table_key"] == "52090"


def test_report_wire_emits_voice_event_only() -> None:
    csv = "GROUP VOICE,START,RX,SYSTEM,3262598598,730039101,730039101,2,730444"
    frames = ReportWire().bridge_event_frames(csv)

    assert len(frames) == 1
    assert frames[0][:1] == REPORT_OPCODES["VOICE_EVENT_SND"]
    voice = json.loads(frames[0][1:].decode())
    assert voice["type"] == "voice_event"


def test_report_wire_skips_unmapped_voice_event() -> None:
    csv = "GROUP VOICE,START,RX,SYSTEM-0,1001,3120001,2,52090"
    frames = ReportWire().bridge_event_frames(csv)

    assert frames == ()


def test_report_factory_push_matches_monitor_contract() -> None:
    """End-to-end: factory._systems_for_report + wire frames safe for monitor."""
    peer_specs = [(730039101, 4), (7301896, 6)]
    factory = ReportServerFactory(_proxy_config())
    factory.set_systems(_inject_runtime_systems(peer_specs))
    factory.set_peer_slot_map(lambda: _peer_slots(peer_specs))

    snapshot = factory._systems_for_report()
    frames = ReportWire().state_frames(snapshot, force=True)
    assert len(frames) == 1
    assert frames[0][:1] == REPORT_OPCODES["STATE_SND"]

    ctable = ctable_with_virtual_masters(max_slots=MAX_PEERS)
    before = count_masters(ctable)
    update_ctable_from_config(snapshot, ctable)

    assert len(_system_n_names(snapshot)) == MAX_PEERS
    assert count_masters(ctable) == before
    assert count_master_peers(ctable) == len(peer_specs)


def test_voice_event_remap_updates_monitor_hotspot_timeslot() -> None:
    """Dashboard chips need SYSTEM-N in voice events (not runtime inject SYSTEM)."""
    peer_specs = [(730039101, 4)]
    runtime = _inject_runtime_systems(peer_specs)
    full = _production_snapshot(peer_specs)
    ctable = empty_ctable()
    apply_config_to_ctable(full, ctable)

    raw = "GROUP VOICE,START,RX,SYSTEM,3262598598,730039101,730039101,2,730444"
    remapped = remap_inject_proxy_voice_event(
        raw, _proxy_config(), runtime, _peer_slots(peer_specs)
    )
    parts = remapped.split(",")
    assert parts[3] == "SYSTEM-4"
    assert 730039101 in ctable["MASTERS"]["SYSTEM-4"]["PEERS"]
    assert "SYSTEM" not in ctable["MASTERS"]


@pytest.mark.parametrize("max_peers", [4, 16, 102])
def test_expansion_always_emits_full_virtual_master_range(max_peers: int) -> None:
    peer = bytes_4(730039101)
    systems = {
        "SYSTEM": {
            "MODE": "MASTER",
            "ENABLED": True,
            "MAX_PEERS": max_peers,
            "_REPORT_BASE_PORT": BASE_PORT,
            "PEERS": {peer: _peer(730039101)},
        }
    }
    expanded = expand_inject_proxy_systems(_proxy_config(), systems, {peer: 1})
    assert len(_system_n_names(expanded)) == max_peers
    topo = build_topology(expanded, seq=1)
    assert len([s for s in topo["systems"] if s["name"].startswith("SYSTEM-")]) == max_peers
