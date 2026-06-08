"""Report server wire encoding."""

from __future__ import annotations

import json

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
    factory._send_config_to(client, full_snapshot=True)
    factory._send_bridge_to(client, full_snapshot=True)

    assert len(client.messages) == 3
    hello = json.loads(client.messages[0][1:].decode())
    assert hello["report_protocol"] == 2
    assert "REPORT_V2" in hello["features"]
    assert client.messages[1][:1] == REPORT_OPCODES["TOPOLOGY_SND"]
    assert json.loads(client.messages[1][1:])["type"] == "topology"
    assert client.messages[2][:1] == REPORT_OPCODES["ROUTING_TABLE_SND"]
    assert json.loads(client.messages[2][1:])["type"] == "routing_table"


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
    factory._send_bridge_to(client, full_snapshot=True)
    factory.set_bridges(
        {
            "52090": [
                {"SYSTEM": "MASTER-A", "TS": 2, "TGID": 52090, "ACTIVE": False, "TO_TYPE": "ON"},
            ],
        }
    )
    factory._send_bridge_to(client, full_snapshot=False)
    assert client.messages[1][:1] == REPORT_OPCODES["DELTA_SND"]
    delta = json.loads(client.messages[1][1:].decode())
    assert delta["type"] == "delta"
    assert delta["patch"]["type"] == "routing_table"

