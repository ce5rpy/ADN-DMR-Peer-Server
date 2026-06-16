# ADN DMR Peer Server - tests infrastructure report server mqtt
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

"""ReportServerFactory MQTT fan-out."""

from __future__ import annotations

import json
from typing import Any

from adn_server.application.ports import ReportMqttPublisher
from adn_server.infrastructure.twisted_adapters.report.opcodes import REPORT_OPCODES
from adn_server.infrastructure.twisted_adapters.report_server import ReportServerFactory


class RecordingMqtt(ReportMqttPublisher):
    def __init__(self) -> None:
        self.frames: list[tuple[bytes, ...]] = []
        self.dashboard_calls = 0
        self.started = False

    def start(self, wire: Any, get_systems: Any, routing_table_for_report: Any) -> None:
        del wire, get_systems, routing_table_for_report
        self.started = True

    def publish_frames(self, frames: tuple[bytes, ...]) -> None:
        if frames:
            self.frames.append(frames)

    def publish_dashboard(self, systems: dict[str, Any]) -> None:
        del systems
        self.dashboard_calls += 1

    def stop(self) -> None:
        pass


def test_send_config_publishes_state_not_tcp_wire():
    mqtt = RecordingMqtt()
    factory = ReportServerFactory({"REPORTS": {}}, mqtt=mqtt)
    factory.set_systems({"SYS": {"MODE": "MASTER", "ENABLED": True}})
    factory.send_config()
    assert mqtt.frames == []
    assert mqtt.dashboard_calls == 1


def test_send_routing_table_does_not_mirror_tcp_wire_to_mqtt():
    mqtt = RecordingMqtt()
    factory = ReportServerFactory({"REPORTS": {}}, mqtt=mqtt)
    factory.set_routing_table({"73010": {"ACTIVE": True}})
    factory.send_routing_table()
    assert mqtt.frames == []


def test_send_routing_event_publishes_voice_event_to_mqtt():
    mqtt = RecordingMqtt()
    factory = ReportServerFactory({"REPORTS": {"PROTOCOL": "v2"}}, mqtt=mqtt)
    factory.set_systems({})
    factory.set_routing_table({})
    factory.send_routing_event("GROUP VOICE,START,RX,MASTER-A,2155905152,1001,3120001,2,52090")
    assert len(mqtt.frames) == 1
    frame = mqtt.frames[0][0]
    assert frame[:1] == REPORT_OPCODES["VOICE_EVENT_SND"]
    payload = json.loads(frame[1:].decode("utf-8"))
    assert payload["type"] == "voice_event"
