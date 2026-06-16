# ADN DMR Peer Server - tests infrastructure mqtt topics
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
