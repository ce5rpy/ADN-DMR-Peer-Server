"""TCP report channel opcodes (shared by all wire encoders)."""

from __future__ import annotations

REPORT_OPCODES = {
    "CONFIG_REQ": b"\x00",
    "CONFIG_SND": b"\x01",
    "BRIDGE_REQ": b"\x02",
    "BRIDGE_SND": b"\x03",
    "CONFIG_UPD": b"\x04",
    "BRIDGE_UPD": b"\x05",
    "LINK_EVENT": b"\x06",
    "BRDG_EVENT": b"\x07",
    "TOPOLOGY_SND": b"\x10",
    "ROUTING_TABLE_SND": b"\x11",
    "VOICE_EVENT_SND": b"\x12",
    "DELTA_SND": b"\x13",
    "HELLO": b"\xff",
}

SERVER_NAME = "adn-server"


def server_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("adn-server")
        except PackageNotFoundError:
            return "0.0.0"
    except Exception:
        return "0.0.0"
