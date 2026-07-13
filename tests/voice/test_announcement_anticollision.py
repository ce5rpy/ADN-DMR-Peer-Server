# ADN DMR Peer Server - tests voice announcement anticollision
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

"""Voice announcement anti-collision."""

from __future__ import annotations

from tests.harness.voice_helpers import make_voice_uc, voice_master_scenario

from adn_server.application.server_voice import DEFAULT_SERVER_VOICE_ID
from adn_server.domain import HBPF_SLT_VHEAD, HBPF_SLT_VTERM, bytes_3


def test_build_targets_skips_busy_qso_slot() -> None:
    scenario, master = voice_master_scenario()
    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VHEAD
    master.STATUS[2]["TX_TYPE"] = HBPF_SLT_VTERM
    uc = make_voice_uc(scenario, master)

    targets, busy = uc._build_announcement_targets(91, "91", "ANN-TEST")

    assert targets == []
    assert busy == 1


def test_build_targets_includes_idle_slot() -> None:
    scenario, master = voice_master_scenario()
    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VTERM
    master.STATUS[2]["TX_TYPE"] = HBPF_SLT_VTERM
    uc = make_voice_uc(scenario, master)

    targets, busy = uc._build_announcement_targets(91, "91", "ANN-TEST")

    assert busy == 0
    assert len(targets) == 1
    assert targets[0]["name"] == "MASTER-A"
    assert targets[0]["ts"] == 2


def test_broadcast_aborts_when_qso_starts_mid_transmission() -> None:
    scenario, master = voice_master_scenario()
    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VTERM
    master.STATUS[2]["TX_TYPE"] = HBPF_SLT_VTERM
    uc = make_voice_uc(scenario, master)
    targets = [{"sys_obj": master, "name": "MASTER-A", "slot": master.STATUS[2], "ts": 2}]
    pkts = {1: [b"\x00" * 55], 2: [b"\x00" * 55]}
    source = bytes_3(DEFAULT_SERVER_VOICE_ID)
    dst = bytes_3(91)

    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VHEAD
    uc._announcement_send_broadcast(targets, pkts, 0, source, dst, 91, 0, "ANN-TEST", None)

    assert uc._announcement_running[0] is False
    assert master.sent == []


def test_mark_slots_busy_stamps_server_voice_tx_row() -> None:
    scenario, master = voice_master_scenario()
    uc = make_voice_uc(scenario, master)
    slot = master.STATUS[2]
    slot["TX_TYPE"] = HBPF_SLT_VTERM
    targets = [{"sys_obj": master, "name": "MASTER-A", "slot": slot, "ts": 2}]

    uc._mark_slots_busy(targets)

    assert slot["TX_TYPE"] == HBPF_SLT_VHEAD
    assert int.from_bytes(slot["TX_RFS"], "big") == DEFAULT_SERVER_VOICE_ID
    assert slot["TX_TIME"] > 0
