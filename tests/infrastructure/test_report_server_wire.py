"""Report server wire encoding."""

from __future__ import annotations

import json

from adn_server.domain.value_objects import bytes_4
from adn_server.infrastructure.twisted_adapters.report_server import (
    REPORT_OPCODES,
    ReportServerFactory,
)


class _CapturingClient:
    def __init__(self) -> None:
        self.messages: list[bytes] = []

    def sendString(self, data: bytes) -> None:
        self.messages.append(data)


def _report_config() -> dict:
    return {"REPORTS": {"REPORT": True, "REPORT_CLIENTS": ["*"]}}


def test_connect_sends_hello_topology_and_routing() -> None:
    factory = ReportServerFactory(_report_config())
    factory.set_systems(
        {
            "MASTER-A": {"MODE": "MASTER", "ENABLED": True, "IP": "10.0.0.1", "PORT": 62030},
        }
    )
    factory.set_bridges(
        {
            "52090": [
                {"SYSTEM": "MASTER-A", "TS": 2, "TGID": 52090, "ACTIVE": True, "TO_TYPE": "ON"},
            ],
        }
    )
    client = _CapturingClient()
    factory.clients.append(client)
    factory._send_hello_to(client)
    factory._send_state_to(client, force=True)

    assert len(client.messages) == 2
    hello = json.loads(client.messages[0][1:].decode())
    assert hello["report_protocol"] == 2
    assert "REPORT_V2" in hello["features"]
    assert client.messages[1][:1] == REPORT_OPCODES["STATE_SND"]
    assert json.loads(client.messages[1][1:])["type"] == "dashboard_state"


def test_bridge_event_emits_voice_event_json() -> None:
    factory = ReportServerFactory(_report_config())
    client = _CapturingClient()
    factory.clients.append(client)
    factory.send_bridge_event("GROUP VOICE,START,RX,MASTER-A,2155905152,1001,3120001,2,52090")
    assert len(client.messages) == 1
    assert client.messages[0][:1] == REPORT_OPCODES["VOICE_EVENT_SND"]
    voice = json.loads(client.messages[0][1:].decode())
    assert voice["type"] == "voice_event"
    assert voice["phase"] == "START"
    assert voice["dst_id"] == 52090


def test_incremental_bridge_update_sends_delta() -> None:
    factory = ReportServerFactory(_report_config())
    factory.set_bridges(
        {
            "52090": [
                {"SYSTEM": "MASTER-A", "TS": 2, "TGID": 52090, "ACTIVE": True, "TO_TYPE": "ON"},
            ],
        }
    )
    client = _CapturingClient()
    factory.clients.append(client)
    factory._send_state_to(client, force=True)
    factory.set_bridges(
        {
            "52090": [
                {"SYSTEM": "MASTER-A", "TS": 2, "TGID": 52090, "ACTIVE": False, "TO_TYPE": "ON"},
            ],
        }
    )
    factory.send_bridge(incremental=True)
    assert len(client.messages) == 1


def test_inject_proxy_topology_expanded_for_monitor() -> None:
    peer = bytes_4(730039101)
    config = {
        "REPORTS": {"REPORT": True, "REPORT_CLIENTS": ["*"]},
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
    }
    factory = ReportServerFactory(config)
    factory.set_systems(
        {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "_REPORT_BASE_PORT": 56400,
                "PEERS": {
                    peer: {
                        "CONNECTION": "YES",
                        "CONNECTED": 1_700_000_000,
                        "IP": "203.0.113.10",
                        "PORT": 62031,
                        "CALLSIGN": b"CE5RPY  ",
                    }
                },
            }
        }
    )
    factory.set_peer_slot_map(lambda: {peer: 2})
    client = _CapturingClient()
    factory.clients.append(client)
    factory._send_state_to(client, force=True)
    assert client.messages[0][:1] == REPORT_OPCODES["STATE_SND"]
    state_doc = json.loads(client.messages[0][1:].decode())
    names = set((state_doc.get("ctable") or {}).get("MASTERS", {}))
    names |= set((state_doc.get("ctable") or {}).get("OPENBRIDGES", {}))
    assert "SYSTEM" not in names
    assert "SYSTEM-2" in names
    system = state_doc["ctable"]["MASTERS"]["SYSTEM-2"]
    assert system["port"] == 56402
    peer_keys = {int(k) for k in system["peers"]}
    assert 730039101 in peer_keys


def test_send_bridge_event_remaps_inject_proxy_system_name() -> None:
    peer = bytes_4(730039101)
    config = {
        "REPORTS": {"REPORT": True, "REPORT_CLIENTS": ["*"]},
        "PROXY": {"TARGET_SYSTEM": "SYSTEM"},
    }
    factory = ReportServerFactory(config)
    factory.set_systems(
        {
            "SYSTEM": {
                "MODE": "MASTER",
                "ENABLED": True,
                "MAX_PEERS": 102,
                "PEERS": {
                    peer: {
                        "CONNECTION": "YES",
                        "CONNECTED": 1_700_000_000,
                        "IP": "203.0.113.10",
                        "PORT": 62031,
                    }
                },
            }
        }
    )
    factory.set_peer_slot_map(lambda: {peer: 4})
    client = _CapturingClient()
    factory.clients.append(client)
    factory.send_bridge_event(
        "GROUP VOICE,START,TX,SYSTEM,2693411696,9990,7300392,2,9990"
    )
    assert len(client.messages) == 1
    payload = json.loads(client.messages[0][1:].decode())
    assert payload["type"] == "voice_event"
    assert payload["system"] == "SYSTEM-4"
    assert payload["peer_id"] == 9990

