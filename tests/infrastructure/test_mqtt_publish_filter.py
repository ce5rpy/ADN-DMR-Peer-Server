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
