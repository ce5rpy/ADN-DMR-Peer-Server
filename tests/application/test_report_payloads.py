"""Unit tests for report payload builders."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from adn_server.application.report import (
    build_routing_table,
    build_topology,
    hello_connected_system_names,
    parse_bridge_event_csv,
    routing_table_delta,
)
from adn_server.domain import bytes_3

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "report-v2.json"
_EXAMPLES_DIR = _SCHEMA_PATH.parent / "examples"


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        schema = json.load(fh)
    return jsonschema.Draft202012Validator(schema)


def test_build_topology_matches_example(validator: jsonschema.Draft202012Validator) -> None:
    with (_EXAMPLES_DIR / "topology.json").open(encoding="utf-8") as fh:
        expected = json.load(fh)
    systems = {
        "MASTER-A": {
            "MODE": "MASTER",
            "ENABLED": True,
            "IP": "10.0.0.1",
            "PORT": 62030,
            "REPEAT": True,
            "PEERS": {
                bytes_3(3120001): {
                    "CONNECTION": "YES",
                    "IP": "10.0.0.50",
                    "PORT": 62031,
                }
            },
        },
        "OBP-CL": {
            "MODE": "OPENBRIDGE",
            "ENABLED": True,
            "IP": "10.0.0.2",
            "PORT": 62044,
            "ENHANCED_OBP": True,
            "PEERS": {},
        },
    }
    doc = build_topology(systems, seq=expected["seq"], ts=expected["ts"])
    assert doc == expected
    validator.validate(doc)


def test_build_routing_table_matches_example(validator: jsonschema.Draft202012Validator) -> None:
    with (_EXAMPLES_DIR / "routing_table.json").open(encoding="utf-8") as fh:
        expected = json.load(fh)
    bridges = {
        "52090": [
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": 52090,
                "ACTIVE": True,
                "TO_TYPE": "ON",
                "TIMER": 1717555320.0,
            },
            {
                "SYSTEM": "MASTER-B",
                "TS": 2,
                "TGID": 52090,
                "ACTIVE": True,
                "TO_TYPE": "ON",
            },
        ],
        "#310": [
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": 310,
                "ACTIVE": False,
                "TO_TYPE": "NONE",
            }
        ],
    }
    doc = build_routing_table(bridges, seq=expected["seq"], ts=expected["ts"])
    assert doc == expected
    validator.validate(doc)


def test_parse_group_voice_start_matches_example(validator: jsonschema.Draft202012Validator) -> None:
    with (_EXAMPLES_DIR / "voice_event.json").open(encoding="utf-8") as fh:
        expected = json.load(fh)
    csv = "GROUP VOICE,START,RX,MASTER-A,2155905152,1001,3120001,2,52090"
    doc = parse_bridge_event_csv(csv)
    assert doc is not None
    doc["ts"] = expected["ts"]
    assert doc == expected
    validator.validate(doc)


def test_routing_delta_matches_example(validator: jsonschema.Draft202012Validator) -> None:
    with (_EXAMPLES_DIR / "routing_table.json").open(encoding="utf-8") as fh:
        previous = json.load(fh)
    with (_EXAMPLES_DIR / "delta.json").open(encoding="utf-8") as fh:
        expected = json.load(fh)

    def _legs_to_bridge(route: dict) -> list[dict]:
        rows = []
        for leg in route["legs"]:
            row = {
                "SYSTEM": leg["system"],
                "TS": leg["ts"],
                "TGID": leg["tgid"],
                "ACTIVE": leg["active"],
                "TO_TYPE": leg["to_type"],
            }
            if "timer_expires_at" in leg:
                row["TIMER"] = leg["timer_expires_at"]
            rows.append(row)
        return rows

    bridges = {
        "52090": _legs_to_bridge(expected["patch"]["routes"][0]),
        "#310": _legs_to_bridge(previous["routes"][1]),
    }
    current = build_routing_table(bridges, seq=expected["patch"]["seq"], ts=expected["patch"]["ts"])
    delta = routing_table_delta(previous, current, seq=expected["seq"], ts=expected["ts"])
    assert delta == expected
    validator.validate(delta)


def test_build_topology_includes_openbridge_network_id() -> None:
    net = (73010).to_bytes(4, "big")
    systems = {
        "OBP-CL": {
            "MODE": "OPENBRIDGE",
            "ENABLED": True,
            "NETWORK_ID": net,
            "PEERS": {},
        }
    }
    doc = build_topology(systems, seq=1, ts=1.0)
    assert doc["systems"][0]["network_id"] == 73010


def test_build_topology_includes_peer_display_fields() -> None:
    systems = {
        "MASTER-A": {
            "MODE": "MASTER",
            "ENABLED": True,
            "PEERS": {
                bytes_3(3120001): {
                    "CONNECTION": "YES",
                    "CALLSIGN": b"CE5RPY  ",
                    "RX_FREQ": b"145625000",
                    "TX_FREQ": b"145625000",
                    "LOCATION": b"Chile               ",
                    "SLOTS": b"2",
                }
            },
        }
    }
    doc = build_topology(systems, seq=1, ts=1.0)
    peer = doc["systems"][0]["peers"][0]
    assert peer["callsign"] == "CE5RPY"
    assert peer["rx_freq"] == "145625000"
    assert peer["tx_freq"] == "145625000"
    assert peer["slots"] == "2"


def test_hello_connected_system_names_only_live_systems() -> None:
    systems = {
        "SYSTEM-0": {
            "MODE": "MASTER",
            "ENABLED": True,
            "PEERS": {
                1001: {"CONNECTION": "YES"},
                1002: {"CONNECTION": "NO"},
            },
        },
        "SYSTEM-1": {
            "MODE": "MASTER",
            "ENABLED": True,
            "PEERS": {2001: {"CONNECTION": "NO"}},
        },
        "OBP-CL": {
            "MODE": "OPENBRIDGE",
            "ENABLED": True,
            "PEERS": {},
        },
        "XLX-1": {
            "MODE": "XLXPEER",
            "ENABLED": True,
            "XLXSTATS": {"CONNECTION": "YES"},
        },
        "DISABLED": {
            "MODE": "MASTER",
            "ENABLED": False,
            "PEERS": {1: {"CONNECTION": "YES"}},
        },
    }
    assert hello_connected_system_names(systems) == ["SYSTEM-0", "XLX-1"]
