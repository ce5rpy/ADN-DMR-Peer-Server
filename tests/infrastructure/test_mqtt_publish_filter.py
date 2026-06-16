# ADN DMR Peer Server - tests infrastructure mqtt publish filter
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

"""MQTT publish type filtering."""

from __future__ import annotations

import json

from adn_server.infrastructure.twisted_adapters.report.mqtt_config import MqttBroker, MqttSettings
from adn_server.infrastructure.twisted_adapters.report.mqtt_publisher import PahoReportMqttPublisher
from adn_server.infrastructure.twisted_adapters.report.opcodes import REPORT_OPCODES


class _FakeClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    def publish(self, topic: str, payload: bytes, qos: int, retain: bool) -> object:
        del qos, retain
        self.published.append((topic, payload))
        return type("Info", (), {"rc": 0})()


def test_publish_frames_skips_routing_by_default():
    pub = PahoReportMqttPublisher(
        MqttSettings(
            broker=MqttBroker(host="h", port=1883, use_tls=False, display_url="mqtt://h:1883"),
            topic_prefix="adn/1",
            client_id="c",
            username=None,
            password=None,
            qos=0,
        )
    )
    pub._connected = True
    pub._client = _FakeClient()
    routing = REPORT_OPCODES["ROUTING_TABLE_SND"] + b'{"type":"routing_table","seq":1,"routes":[]}'
    voice = REPORT_OPCODES["VOICE_EVENT_SND"] + json.dumps({"type": "voice_event", "phase": "start"}).encode()
    pub.publish_frames((routing, voice))
    assert len(pub._client.published) == 1
    assert pub._client.published[0][0] == "adn/1/voice_event"
