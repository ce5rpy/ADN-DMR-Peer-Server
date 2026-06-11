"""MQTT username/password authentication wiring."""

from __future__ import annotations

from typing import Any

from adn_server.infrastructure.twisted_adapters.report.mqtt_config import MqttBroker, MqttSettings
from adn_server.infrastructure.twisted_adapters.report.mqtt_publisher import PahoReportMqttPublisher


class _AuthCapturingClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.auth: tuple[str, str | None] | None = None
        self.tls: dict[str, Any] | None = None

    def username_pw_set(self, username: str, password: str | None) -> None:
        self.auth = (username, password)

    def tls_set(self, **kwargs: Any) -> None:
        self.tls = kwargs

    def connect(self, host: str, port: int, keepalive: int) -> None:
        self.connect_args = (host, port, keepalive)

    def loop_start(self) -> None:
        pass


class _FakeMqttModule:
    MQTTv311 = 4
    CallbackAPIVersion = type("CallbackAPIVersion", (), {"VERSION2": 2})

    def Client(self, **kwargs: Any) -> _AuthCapturingClient:
        return _AuthCapturingClient(**kwargs)


def _settings(**kwargs: Any) -> MqttSettings:
    defaults = {
        "broker": MqttBroker(host="broker", port=1883, use_tls=False, display_url="mqtt://broker:1883"),
        "topic_prefix": "adn/1",
        "client_id": "test",
        "username": "ops",
        "password": "secret",
        "qos": 0,
    }
    defaults.update(kwargs)
    return MqttSettings(**defaults)


def test_start_applies_username_password(monkeypatch):
    fake = _FakeMqttModule()
    monkeypatch.setattr(
        "adn_server.infrastructure.twisted_adapters.report.mqtt_publisher.mqtt",
        fake,
    )
    pub = PahoReportMqttPublisher(_settings())
    pub.start(wire=object(), get_systems=lambda: {}, routing_table_for_report=lambda: {})
    assert pub._client is not None
    assert pub._client.auth == ("ops", "secret")


def test_start_tls_with_cafile(monkeypatch):
    fake = _FakeMqttModule()
    monkeypatch.setattr(
        "adn_server.infrastructure.twisted_adapters.report.mqtt_publisher.mqtt",
        fake,
    )
    broker = MqttBroker(host="secure", port=8883, use_tls=True, display_url="mqtts://secure:8883")
    pub = PahoReportMqttPublisher(_settings(broker=broker, cafile="/etc/ssl/certs/ca.pem"))
    pub.start(wire=object(), get_systems=lambda: {}, routing_table_for_report=lambda: {})
    assert pub._client is not None
    assert pub._client.tls == {"ca_certs": "/etc/ssl/certs/ca.pem"}
