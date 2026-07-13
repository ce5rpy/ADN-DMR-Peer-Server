# ADN DMR Peer Server - tests voice broadcast queue
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

"""Voice broadcast queue (same-TG serialization)."""

from __future__ import annotations

from tests.harness.voice_helpers import make_voice_uc, voice_master_scenario

from adn_server.application.server_voice import DEFAULT_SERVER_VOICE_ID
from adn_server.domain import bytes_3


def test_enqueue_broadcast_queues_second_same_tg() -> None:
    scenario, master = voice_master_scenario()
    uc = make_voice_uc(scenario, master)
    targets = [{"sys_obj": master, "name": "MASTER-A", "slot": master.STATUS[2], "ts": 2}]
    pkts = {1: [b"\x00" * 55], 2: [b"\x00" * 55]}
    source = bytes_3(DEFAULT_SERVER_VOICE_ID)
    dst = bytes_3(91)

    uc._broadcast_active_tgs.add("91")
    uc._enqueue_broadcast("ann", targets, pkts, source, dst, 91, 0, "ANN-2")

    assert len(uc._broadcast_queue) == 1
    assert uc._scheduled == []


def test_broadcast_queue_drains_after_first_finishes() -> None:
    scenario, master = voice_master_scenario()
    uc = make_voice_uc(scenario, master)
    targets = [{"sys_obj": master, "name": "MASTER-A", "slot": master.STATUS[2], "ts": 2}]
    pkts = {1: [b"\x00" * 55], 2: [b"\x00" * 55]}
    source = bytes_3(DEFAULT_SERVER_VOICE_ID)
    dst = bytes_3(91)

    uc._broadcast_active_tgs.add("91")
    uc._broadcast_queue.append(
        {
            "type": "ann",
            "targets": targets,
            "pkts_by_ts": pkts,
            "source_id": source,
            "dst_id": dst,
            "tg": 91,
            "num": 1,
            "label": "ANN-2",
        }
    )
    uc._broadcast_finished(91)
    assert len(uc._scheduled) == 1
    uc._scheduled.pop(0)[1][0]()

    assert "91" in uc._broadcast_active_tgs
    assert uc._broadcast_queue == []
    assert len(uc._scheduled) == 1
    assert uc._scheduled[0][0] == 0.5
