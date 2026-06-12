# ADN DMR Peer Server - infrastructure twisted adapters report mqtt topics
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

"""Map report v2 wire frames to MQTT topic suffixes."""

from __future__ import annotations

import json
from typing import Any

from .opcodes import REPORT_OPCODES


def mqtt_shared_state_topic(prefix: str) -> str:
    """Retained ``dashboard_state`` snapshot for all consumers (topology-driven refreshes)."""
    return f"{prefix}/state"


def frame_message_type(frame: bytes) -> str | None:
    """Report v2 message kind for MQTT publish filtering."""
    if len(frame) < 2:
        return None
    opcode = frame[0:1]
    if opcode == REPORT_OPCODES["HELLO"]:
        return "hello"
    if opcode == REPORT_OPCODES["TOPOLOGY_SND"]:
        return "topology"
    if opcode == REPORT_OPCODES["ROUTING_TABLE_SND"]:
        return "routing_table"
    if opcode == REPORT_OPCODES["VOICE_EVENT_SND"]:
        return "voice_event"
    if opcode == REPORT_OPCODES["DELTA_SND"]:
        return "delta"
    return None


def topic_for_frame(frame: bytes, prefix: str) -> str | None:
    """Return full MQTT topic for a TCP report frame (opcode + JSON), or None if unknown."""
    if len(frame) < 2:
        return None
    opcode = frame[0:1]
    if opcode == REPORT_OPCODES["HELLO"]:
        return f"{prefix}/hello"
    if opcode == REPORT_OPCODES["TOPOLOGY_SND"]:
        return f"{prefix}/topology"
    if opcode == REPORT_OPCODES["ROUTING_TABLE_SND"]:
        return f"{prefix}/routing_table"
    if opcode == REPORT_OPCODES["VOICE_EVENT_SND"]:
        return f"{prefix}/voice_event"
    if opcode == REPORT_OPCODES["DELTA_SND"]:
        return _delta_topic(frame[1:], prefix)
    return None


def _delta_topic(payload: bytes, prefix: str) -> str:
    try:
        doc: dict[str, Any] = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return f"{prefix}/delta"
    patch_type = doc.get("patch", {}).get("type")
    if patch_type == "topology":
        return f"{prefix}/delta/topology"
    if patch_type == "routing_table":
        return f"{prefix}/delta/routing_table"
    return f"{prefix}/delta"
