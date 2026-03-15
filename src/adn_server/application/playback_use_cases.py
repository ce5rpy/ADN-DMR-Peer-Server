# ADN DMR Peer Server - playback (parrot) use case
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS & Mike Zingman, N4IRR
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
# Derived from playback.py. GPLv3.

"""Exact port of playback.py dmrd_received: record group voice, then play back with new stream ID."""

from __future__ import annotations

import logging
from random import randint
from time import sleep, time
from typing import Any

from ..domain import int_id, bytes_4
from ..infrastructure.hbp_constants import HBPF_DATA_SYNC, HBPF_SLT_VTERM

logger = logging.getLogger(__name__)


class PlaybackUseCases:
    """Exact port of legacy playback class. One instance per system."""

    def __init__(self, system_name: str, get_protocol: Any = None) -> None:
        self._system = system_name
        self._get_protocol = get_protocol
        self.STATUS: dict[str, Any] = {}
        self.CALL_DATA: list[bytes] = []

    def dmrd_received(
        self,
        system_name: str,
        peer_id: bytes,
        rf_src: bytes,
        dst_id: bytes,
        seq: int,
        slot: int,
        call_type: str,
        frame_type: int,
        dtype_vseq: int,
        stream_id: bytes,
        data: bytes,
    ) -> None:
        """Exact port of playback.dmrd_received (playback.py lines 114-161)."""
        pkt_time = time()

        if call_type == "group":
            proto = self._get_protocol() if self._get_protocol else None
            slot_status = getattr(proto, "STATUS", {}).get(slot, {}) if proto else {}

            if stream_id != slot_status.get("RX_STREAM_ID", b"\x00"):
                self.STATUS["RX_START"] = pkt_time
                logger.info(
                    "(%s) *START RECORDING* STREAM ID: %s SUB: %s REPEATER: %s TGID %s, TS %s",
                    self._system, int_id(stream_id), int_id(rf_src), int_id(peer_id), int_id(dst_id), slot,
                )
                self.CALL_DATA.append(data)
                return

            if (frame_type == HBPF_DATA_SYNC) and (dtype_vseq == HBPF_SLT_VTERM) and (slot_status.get("RX_TYPE") != HBPF_SLT_VTERM) and self.CALL_DATA:
                call_duration = pkt_time - self.STATUS.get("RX_START", pkt_time)
                self.CALL_DATA.append(data)
                logger.info("(%s) *END   RECORDING* STREAM ID: %s", self._system, int_id(stream_id))
                sleep(2)
                _new_stream_id = bytes_4(randint(0x00, 0xFFFFFFFF))
                logger.info(
                    "(%s) *START  PLAYBACK* STREAM ID: %s SUB: %s REPEATER: %s TGID %s, TS %s, Duration: %s",
                    self._system, int_id(_new_stream_id), int_id(rf_src), int_id(peer_id), int_id(dst_id), slot, call_duration,
                )

                if proto:
                    for i in self.CALL_DATA:
                        i = i[:16] + _new_stream_id + i[20:]
                        proto.send_system(i)
                        sleep(0.06)
                self.CALL_DATA = []
                logger.info("(%s) *END    PLAYBACK* STREAM ID: %s", self._system, int_id(_new_stream_id))

            else:
                if self.CALL_DATA:
                    self.CALL_DATA.append(data)
