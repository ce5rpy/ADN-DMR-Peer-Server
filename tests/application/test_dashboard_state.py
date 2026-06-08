"""Minimal dashboard_state payload."""

from __future__ import annotations

from adn_server.application.report.dashboard_state import build_dashboard_state


def test_dashboard_state_omits_idle_masters():
    systems = {
        "SYSTEM-0": {
            "MODE": "MASTER",
            "ENABLED": True,
            "PEERS": {
                b"\x00\x00\x00\x01": {"CONNECTION": "NO", "CONNECTED": 0},
            },
        },
        "ECHO": {
            "MODE": "MASTER",
            "ENABLED": True,
            "PEERS": {
                b"\x00\x00\x00\x02": {"CONNECTION": "YES", "CONNECTED": 1000, "IP": "10.0.0.2"},
            },
        },
    }
    state = build_dashboard_state(systems, server_id="7302")
    assert state["type"] == "dashboard_state"
    assert state["server_id"] == "7302"
    assert "SYSTEM-0" not in state["ctable"]["MASTERS"]
    assert "ECHO" in state["ctable"]["MASTERS"]
    assert 2 in state["ctable"]["MASTERS"]["ECHO"]["peers"]


def test_dashboard_state_includes_master_static_tgs_on_peers():
    systems = {
        "MASTER-A": {
            "MODE": "MASTER",
            "ENABLED": True,
            "TS1_STATIC": "91,92",
            "TS2_STATIC": "730",
            "PEERS": {
                b"\x00\x2f\xd0\x31": {"CONNECTION": "YES", "CONNECTED": 1000},
            },
        },
    }
    state = build_dashboard_state(systems)
    peers = state["ctable"]["MASTERS"]["MASTER-A"]["peers"]
    assert len(peers) == 1
    peer = next(iter(peers.values()))
    assert peer["ts1_static"] == ["91", "92"]
    assert peer["ts2_static"] == ["730"]


def test_dashboard_state_includes_enabled_openbridge():
    systems = {
        "OBP-CL": {
            "MODE": "OPENBRIDGE",
            "ENABLED": True,
            "IP": "44.31.61.68",
            "PORT": 62999,
            "NETWORK_ID": 73010,
            "ENHANCED_OBP": True,
            "PEERS": {},
        },
    }
    state = build_dashboard_state(systems)
    obp = state["ctable"]["OPENBRIDGES"]["OBP-CL"]
    assert obp["mode"] == "OPENBRIDGE"
    assert obp["network_id"] == 73010
    assert obp["enhanced_obp"] is True
    assert obp["streams"] == {}


def test_dashboard_state_includes_connected_upstream_peer():
    systems = {
        "XLX-730": {
            "MODE": "XLXPEER",
            "ENABLED": True,
            "CALLSIGN": "XLX730",
            "RADIO_ID": 730,
            "XLXSTATS": {"CONNECTION": "YES", "CONNECTED": 1700000000},
            "PEERS": {},
        },
    }
    state = build_dashboard_state(systems)
    assert "XLX-730" in state["ctable"]["PEERS"]
    assert state["ctable"]["PEERS"]["XLX-730"]["connected"] is True
    assert state["ctable"]["MASTERS"] == {}
