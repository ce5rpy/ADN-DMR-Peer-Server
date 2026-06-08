"""Tests for MQTT publisher frame fan-out."""

from __future__ import annotations

import json
from typing import Any

from adn_server.infrastructure.twisted_adapters.report.mqtt_config import MqttBroker, MqttSettings
from adn_server.infrastructure.twisted_adapters.report.mqtt_publisher import PahoReportMqttPublisher
from adn_server.infrastructure.twisted_adapters.report.opcodes import REPORT_OPCODES


class _FakeMqttModule:
    MQTTv311 = 4
    MQTT_ERR_SUCCESS = 0
    CallbackAPIVersion = type("CallbackAPIVersion", (), {"VERSION2": 2})

    class Client:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs
            self.published: list[tuple[str, bytes, int, bool]] = []

        def username_pw_set(self, username: str, password: str | None) -> None:
            self.auth = (username, password)

        def connect(self, host: str, port: int, keepalive: int) -> None:
            self.host = (host, port, keepalive)

        def loop_start(self) -> None:
            pass

        def publish(self, topic: str, payload: bytes, qos: int, retain: bool) -> Any:
            self.published.append((topic, payload, qos, retain))
            return type("Info", (), {"rc": 0})()

        def loop_stop(self) -> None:
            pass

        def disconnect(self) -> None:
            pass


def test_publish_frames_maps_topics(monkeypatch):
    fake = _FakeMqttModule()
    monkeypatch.setattr(
        "adn_server.infrastructure.twisted_adapters.report.mqtt_publisher.mqtt",
        fake,
    )
    pub = PahoReportMqttPublisher(
        MqttSettings(
            broker=MqttBroker(host="127.0.0.1", port=1883, use_tls=False, display_url="mqtt://127.0.0.1:1883"),
            topic_prefix="adn/test",
            client_id="test",
            username=None,
            password=None,
            qos=0,
        )
    )
    pub._connected = True
    pub._client = fake.Client()
    voice = {"type": "voice_event", "phase": "start"}
    frame = REPORT_OPCODES["VOICE_EVENT_SND"] + json.dumps(voice).encode("utf-8")
    pub.publish_frames((frame,))
    assert pub._client.published == [
        ("adn/test/voice_event", json.dumps(voice).encode("utf-8"), 0, False),
    ]


def test_on_connect_publishes_shared_state(monkeypatch):
    fake = _FakeMqttModule()
    monkeypatch.setattr(
        "adn_server.infrastructure.twisted_adapters.report.mqtt_publisher.mqtt",
        fake,
    )
    pub = PahoReportMqttPublisher(
        MqttSettings(
            broker=MqttBroker(host="127.0.0.1", port=1883, use_tls=False, display_url="mqtt://127.0.0.1:1883"),
            topic_prefix="adn/7302",
            client_id="test",
            username=None,
            password=None,
            qos=0,
        )
    )
    client = fake.Client()
    pub._client = client
    pub._get_systems = lambda: {"MASTER1": {"MODE": "MASTER", "ENABLED": True, "PEERS": {}}}
    pub._on_connect(client, None, None, type("RC", (), {"value": 0})(), None)
    assert len(client.published) == 1
    topic, body, qos, retain = client.published[0]
    assert topic == "adn/7302/state"
    assert qos == 0
    assert retain is True
    assert json.loads(body.decode("utf-8"))["type"] == "dashboard_state"


def test_emit_dashboard_skips_unchanged_state(monkeypatch):
    fake = _FakeMqttModule()
    monkeypatch.setattr(
        "adn_server.infrastructure.twisted_adapters.report.mqtt_publisher.mqtt",
        fake,
    )
    pub = PahoReportMqttPublisher(
        MqttSettings(
            broker=MqttBroker(host="127.0.0.1", port=1883, use_tls=False, display_url="mqtt://127.0.0.1:1883"),
            topic_prefix="adn/test",
            client_id="test",
            username=None,
            password=None,
            qos=0,
        )
    )
    pub._connected = True
    pub._client = fake.Client()
    systems = {
        "ECHO": {
            "MODE": "MASTER",
            "ENABLED": True,
            "PEERS": {b"\x00\x00\x00\x01": {"CONNECTION": "YES", "CONNECTED": 1}},
        },
    }
    pub._emit_shared_dashboard(systems)
    pub._emit_shared_dashboard(systems)
    state_published = [
        t for t, b, _q, _r in pub._client.published if b and json.loads(b.decode())["type"] == "dashboard_state"
    ]
    assert state_published == ["adn/test/state"]


def test_publish_dashboard_publishes_shared_state(monkeypatch):
    fake = _FakeMqttModule()
    monkeypatch.setattr(
        "adn_server.infrastructure.twisted_adapters.report.mqtt_publisher.mqtt",
        fake,
    )
    pub = PahoReportMqttPublisher(
        MqttSettings(
            broker=MqttBroker(host="127.0.0.1", port=1883, use_tls=False, display_url="mqtt://127.0.0.1:1883"),
            topic_prefix="adn/7302",
            client_id="test",
            username=None,
            password=None,
            qos=0,
        )
    )
    pub._connected = True
    pub._client = fake.Client()
    pub.publish_dashboard({})
    assert len(pub._client.published) == 1
    assert pub._client.published[0][0] == "adn/7302/state"
    assert pub._client.published[0][3] is True
    pub._client.published.clear()
    pub.publish_dashboard(
        {
            "ECHO": {
                "MODE": "MASTER",
                "ENABLED": True,
                "PEERS": {b"\x00\x00\x00\x01": {"CONNECTION": "YES", "CONNECTED": 1}},
            },
        }
    )
    topic, _body, _qos, retain = pub._client.published[0]
    assert topic == "adn/7302/state"
    assert retain is True
    pub.publish_dashboard(
        {
            "ECHO": {
                "MODE": "MASTER",
                "ENABLED": True,
                "PEERS": {b"\x00\x00\x00\x01": {"CONNECTION": "YES", "CONNECTED": 1}},
            },
        }
    )
    assert len(pub._client.published) == 1
