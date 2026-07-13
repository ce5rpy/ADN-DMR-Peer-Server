# ADN DMR Peer Server - tests voice scheduled announcement
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

"""Scheduled file announcements (AMBE on disk)."""

from __future__ import annotations

from tests.harness.voice_helpers import (
    drain_call_later,
    make_voice_uc,
    voice_announcement_config,
    voice_master_scenario,
)

from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD, HBPF_SLT_VTERM


def test_scheduled_announcement_starts_broadcast_on_idle_slot() -> None:
    scenario, master = voice_master_scenario()
    voice_announcement_config(scenario)
    uc = make_voice_uc(scenario, master)

    uc.scheduled_announcement(0)

    assert uc._announcement_running[0] is True
    assert "91" in uc._broadcast_active_tgs
    assert master.STATUS[2]["TX_TYPE"] == HBPF_SLT_VHEAD
    assert len(uc._scheduled) == 1
    delay, _scheduled = uc._scheduled[0]
    assert delay == 0.5
    drain_call_later(uc)
    assert len(master.sent) == 3
    assert len(scenario.capture.for_system("MASTER-B")) == 3


def test_scheduled_announcement_retries_when_slot_busy() -> None:
    scenario, master = voice_master_scenario()
    voice_announcement_config(scenario)
    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VHEAD
    uc = make_voice_uc(scenario, master)

    uc.scheduled_announcement(0)

    assert uc._announcement_running.get(0) is not True
    assert len(uc._scheduled) == 1
    assert master.sent == []
    delay, (_fn, args) = uc._scheduled[0]
    assert delay == 5.0
    assert args == (0, 1)


def test_scheduled_announcement_skips_when_disabled() -> None:
    scenario, master = voice_master_scenario()
    voice_announcement_config(scenario, enabled=False)
    uc = make_voice_uc(scenario, master)

    uc.scheduled_announcement(0)

    assert uc._announcement_running.get(0) is not True
    assert uc._scheduled == []


def test_scheduled_announcement_sends_packets_to_master() -> None:
    scenario, master = voice_master_scenario()
    voice_announcement_config(scenario)
    uc = make_voice_uc(scenario, master)

    uc.scheduled_announcement(0)
    drain_call_later(uc)

    assert uc._announcement_running[0] is False
    assert "91" not in uc._broadcast_active_tgs
    assert len(master.sent) == 3
    assert len(scenario.capture.for_system("MASTER-B")) == 3
    assert master.STATUS[2]["TX_TYPE"] == HBPF_SLT_VTERM
