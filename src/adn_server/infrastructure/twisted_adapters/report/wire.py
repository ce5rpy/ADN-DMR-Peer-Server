"""Report wire: typed JSON topology / routing_table / voice_event / delta."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from adn_server.application.ports import ReportWireEncoder
from adn_server.application.report import (
    REPORT_FEATURES,
    REPORT_PROTOCOL,
    build_routing_table,
    build_topology,
    hello_connected_system_names,
    parse_bridge_event_csv,
    routing_table_delta,
    topology_delta,
)

from .opcodes import REPORT_OPCODES, SERVER_NAME, server_version
from .pickle_legacy import encode_config_snd_frame

logger = logging.getLogger(__name__)


def _json_wire(opcode: bytes, payload: dict[str, Any]) -> bytes:
    return opcode + json.dumps(payload, separators=(",", ":")).encode("utf-8")


class ReportWire(ReportWireEncoder):
    """Stateful report encoder — seq counters and delta patches."""

    def __init__(self) -> None:
        self._topology_seq = 0
        self._routing_seq = 0
        self._last_topology: dict[str, Any] | None = None
        self._last_routing: dict[str, Any] | None = None

    def hello_frames(self, systems: dict[str, Any]) -> tuple[bytes, ...]:
        names = hello_connected_system_names(systems)
        info: dict[str, Any] = {
            "type": "hello",
            "server": SERVER_NAME,
            "version": server_version(),
            "report_protocol": REPORT_PROTOCOL,
            "features": list(REPORT_FEATURES),
        }
        if names:
            info["systems"] = names
        payload = json.dumps(info, separators=(",", ":")).encode("utf-8")
        return (REPORT_OPCODES["HELLO"] + payload,)

    def config_frames(self, systems: dict[str, Any], *, full_snapshot: bool) -> tuple[bytes, ...]:
        ts = time.time()
        if full_snapshot or self._last_topology is None:
            self._topology_seq += 1
            topology = build_topology(systems, seq=self._topology_seq, ts=ts)
            self._last_topology = topology
            logger.debug("(REPORT) CONFIG_SND pickle + TOPOLOGY_SND seq=%s", self._topology_seq)
            return (
                encode_config_snd_frame(systems),
                _json_wire(REPORT_OPCODES["TOPOLOGY_SND"], topology),
            )
        self._topology_seq += 1
        current = build_topology(systems, seq=self._topology_seq, ts=ts)
        delta = topology_delta(self._last_topology, current, seq=self._topology_seq, ts=ts)
        if delta is None:
            self._topology_seq -= 1
            return ()
        self._last_topology = current
        logger.debug("(REPORT) DELTA_SND topology seq=%s", delta["seq"])
        return (_json_wire(REPORT_OPCODES["DELTA_SND"], delta),)

    def bridge_frames(self, bridges: dict[str, Any], *, full_snapshot: bool) -> tuple[bytes, ...]:
        ts = time.time()
        if full_snapshot or self._last_routing is None:
            self._routing_seq += 1
            routing = build_routing_table(bridges, seq=self._routing_seq, ts=ts)
            self._last_routing = routing
            logger.debug("(REPORT) ROUTING_TABLE_SND seq=%s", self._routing_seq)
            return (_json_wire(REPORT_OPCODES["ROUTING_TABLE_SND"], routing),)
        self._routing_seq += 1
        current = build_routing_table(bridges, seq=self._routing_seq, ts=ts)
        delta = routing_table_delta(self._last_routing, current, seq=self._routing_seq, ts=ts)
        if delta is None:
            self._routing_seq -= 1
            return ()
        self._last_routing = current
        logger.debug("(REPORT) DELTA_SND routing seq=%s", delta["seq"])
        return (_json_wire(REPORT_OPCODES["DELTA_SND"], delta),)

    def bridge_event_frames(self, event: str) -> tuple[bytes, ...]:
        voice = parse_bridge_event_csv(event)
        if voice is None:
            logger.warning("(REPORT) BRDG_EVENT not mapped to voice_event: %s", event[:120])
            return ()
        logger.debug(
            "(REPORT) VOICE_EVENT_SND %s %s %s",
            voice["call_family"],
            voice["phase"],
            voice["system"],
        )
        return (_json_wire(REPORT_OPCODES["VOICE_EVENT_SND"], voice),)
