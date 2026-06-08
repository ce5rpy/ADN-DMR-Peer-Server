"""Tests for MQTT topic mapping from report wire frames."""

from __future__ import annotations

import json

from adn_server.infrastructure.twisted_adapters.report.mqtt_topics import (
    mqtt_shared_state_topic,
    topic_for_frame,
)
from adn_server.infrastructure.twisted_adapters.report.opcodes import REPORT_OPCODES


def _frame(opcode: bytes, payload: dict) -> bytes:
    return opcode + json.dumps(payload, separators=(",", ":")).encode("utf-8")


def test_shared_state_topic():
    assert mqtt_shared_state_topic("adn/7302") == "adn/7302/state"


def test_topology_topic():
    frame = _frame(REPORT_OPCODES["TOPOLOGY_SND"], {"type": "topology", "seq": 1})
    assert topic_for_frame(frame, "adn/73010") == "adn/73010/topology"


def test_delta_topology_topic():
    frame = _frame(
        REPORT_OPCODES["DELTA_SND"],
        {"type": "delta", "since_seq": 1, "patch": {"type": "topology", "systems": []}},
    )
    assert topic_for_frame(frame, "pfx") == "pfx/delta/topology"


def test_delta_routing_topic():
    frame = _frame(
        REPORT_OPCODES["DELTA_SND"],
        {"type": "delta", "since_seq": 2, "patch": {"type": "routing_table", "bridges": {}}},
    )
    assert topic_for_frame(frame, "pfx") == "pfx/delta/routing_table"
