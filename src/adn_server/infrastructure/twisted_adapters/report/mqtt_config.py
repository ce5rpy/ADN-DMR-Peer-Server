"""Parse optional REPORTS.MQTT settings (disabled unless explicitly enabled)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class MqttBroker:
    host: str
    port: int
    use_tls: bool
    display_url: str


# Fixed MQTT wire (not configurable): live voice + retained shared ``{prefix}/state`` only.
MQTT_PUBLISH_VOICE_EVENT = "voice_event"
MQTT_PUBLISH_STATE = "state"


@dataclass(frozen=True)
class MqttSettings:
    broker: MqttBroker
    topic_prefix: str
    client_id: str
    username: str | None
    password: str | None
    qos: int
    cafile: str | None = None


def _non_empty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _password_value(value: Any) -> str | None:
    """Return password string; empty YAML password is a valid (empty) secret."""
    if value is None:
        return None
    return str(value)


def parse_mqtt_broker(url: str) -> tuple[MqttBroker, str | None, str | None]:
    """Parse broker URL; return endpoint and optional username/password from userinfo."""
    normalized = url if "://" in url else f"mqtt://{url}"
    parsed = urlparse(normalized)
    scheme = (parsed.scheme or "mqtt").lower()
    host = parsed.hostname or "127.0.0.1"
    if parsed.port is not None:
        port = parsed.port
    elif scheme in ("mqtts", "ssl", "tls"):
        port = 8883
    else:
        port = 1883
    use_tls = scheme in ("mqtts", "ssl", "tls")
    display_url = f"{'mqtts' if use_tls else 'mqtt'}://{host}:{port}"

    url_user = unquote(parsed.username) if parsed.username is not None else None
    url_pass = unquote(parsed.password) if parsed.password is not None else None
    if url_user is not None:
        url_user = url_user.strip() or None
    return MqttBroker(host=host, port=port, use_tls=use_tls, display_url=display_url), url_user, url_pass


def _server_id(config: dict[str, Any]) -> str:
    """Display server id for MQTT topics/client_id (GLOBAL.SERVER_ID is bytes after normalize)."""
    sid = config.get("GLOBAL", {}).get("SERVER_ID", "server")
    if isinstance(sid, bytes):
        raw = sid[:4].ljust(4, b"\x00")[:4]
        return str(int.from_bytes(raw, "big"))
    if isinstance(sid, int):
        return str(sid & 0xFFFFFFFF)
    text = str(sid).strip()
    return text or "server"


def default_topic_prefix(config: dict[str, Any]) -> str:
    return f"adn/{_server_id(config)}"


def default_mqtt_client_id(config: dict[str, Any]) -> str:
    """Derived client id: adn-server-{SERVER_ID}-{random} (not configurable)."""
    return f"adn-server-{_server_id(config)}-{secrets.token_hex(4)}"


def _resolve_credentials(
    mqtt_block: dict[str, Any] | None,
    reports: dict[str, Any],
    url_user: str | None,
    url_pass: str | None,
) -> tuple[str | None, str | None]:
    """Explicit YAML USERNAME/PASSWORD override credentials embedded in the broker URL."""
    username = url_user
    password = url_pass
    if isinstance(mqtt_block, dict):
        if "USERNAME" in mqtt_block:
            username = _non_empty(mqtt_block.get("USERNAME"))
        elif "MQTT_USERNAME" in reports:
            username = _non_empty(reports.get("MQTT_USERNAME"))
        if "PASSWORD" in mqtt_block:
            password = _password_value(mqtt_block.get("PASSWORD"))
        elif "MQTT_PASSWORD" in reports:
            password = _password_value(reports.get("MQTT_PASSWORD"))
    else:
        if "MQTT_USERNAME" in reports:
            username = _non_empty(reports.get("MQTT_USERNAME"))
        if "MQTT_PASSWORD" in reports:
            password = _password_value(reports.get("MQTT_PASSWORD"))
    return username, password


def mqtt_settings_from_config(config: dict[str, Any]) -> MqttSettings | None:
    """Return settings only when MQTT is explicitly enabled and a broker URL is set."""
    reports = config.get("REPORTS", {})
    mqtt_block = reports.get("MQTT")
    if isinstance(mqtt_block, dict):
        enabled = mqtt_block.get("ENABLED") is True
        raw_url = _non_empty(mqtt_block.get("URL")) or _non_empty(reports.get("MQTT_URL"))
        topic_prefix = _non_empty(mqtt_block.get("TOPIC_PREFIX")) or _non_empty(
            reports.get("MQTT_TOPIC_PREFIX")
        )
        cafile = _non_empty(mqtt_block.get("CAFILE")) or _non_empty(reports.get("MQTT_CAFILE"))
        qos_raw = mqtt_block.get("QOS", reports.get("MQTT_QOS", 0))
        qos = int(qos_raw) if qos_raw is not None else 0
    else:
        enabled = reports.get("MQTT_ENABLED") is True
        raw_url = _non_empty(reports.get("MQTT_URL"))
        topic_prefix = _non_empty(reports.get("MQTT_TOPIC_PREFIX"))
        cafile = _non_empty(reports.get("MQTT_CAFILE"))
        qos_raw = reports.get("MQTT_QOS", 0)
        qos = int(qos_raw) if qos_raw is not None else 0
        mqtt_block = None

    if not enabled or not raw_url:
        return None

    broker, url_user, url_pass = parse_mqtt_broker(raw_url)
    username, password = _resolve_credentials(mqtt_block, reports, url_user, url_pass)

    return MqttSettings(
        broker=broker,
        topic_prefix=topic_prefix or default_topic_prefix(config),
        client_id=default_mqtt_client_id(config),
        username=username,
        password=password,
        qos=max(0, min(qos, 2)),
        cafile=cafile,
    )
