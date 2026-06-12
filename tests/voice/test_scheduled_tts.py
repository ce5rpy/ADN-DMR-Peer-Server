# ADN DMR Peer Server - tests voice scheduled tts
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

"""Scheduled TTS announcements and conversion callbacks."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

from tests.harness.voice_helpers import make_voice_uc, voice_master_scenario, voice_tts_config

from adn_server.application.voice_use_cases import VoiceUseCases
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD


def test_scheduled_tts_sync_path_enqueues_broadcast() -> None:
    scenario, master = voice_master_scenario()
    voice_tts_config(scenario)
    uc = make_voice_uc(scenario, master)

    uc.scheduled_tts_announcement(0)

    assert uc._broadcast_active_tgs == {"91"}
    assert len(uc._scheduled) == 1
    assert getattr(uc._scheduled[0][1][0], "__name__", "") == "_tts_send_broadcast"


def test_tts_conversion_error_clears_running_flag() -> None:
    scenario, master = voice_master_scenario()
    uc = make_voice_uc(scenario, master)
    uc._tts_running[0] = True

    uc._tts_conversion_error(RuntimeError("TTS failed"), 0, "TTS-1")

    assert uc._tts_running[0] is False


def test_tts_conversion_done_without_ambe_clears_running() -> None:
    scenario, master = voice_master_scenario()
    uc = make_voice_uc(scenario, master)
    uc._tts_running[0] = True

    uc._tts_conversion_done(None, 0, "msg.ambe", 91, "en_GB", "interval", "TTS-1")

    assert uc._tts_running[0] is False
    assert uc._scheduled == []


def test_tts_conversion_done_retries_when_slot_busy() -> None:
    scenario, master = voice_master_scenario()
    master.STATUS[2]["RX_TYPE"] = HBPF_SLT_VHEAD
    uc = make_voice_uc(scenario, master)
    uc._tts_running[0] = True

    uc._tts_conversion_done("/tmp/fake.ambe", 0, "msg.ambe", 91, "en_GB", "interval", "TTS-1")

    assert uc._tts_running[0] is True
    assert len(uc._scheduled) == 1
    delay, (fn, args) = uc._scheduled[0]
    assert delay == 5.0
    assert getattr(fn, "__name__", "") == "_tts_conversion_done"
    assert args[-1] == 1


def test_scheduled_tts_skips_outside_top_of_hour() -> None:
    scenario, master = voice_master_scenario()
    scenario.config["VOICE"] = {
        "TTS_ANNOUNCEMENTS": [
            {
                "ENABLED": True,
                "TG": 91,
                "FILE": "hourly.ambe",
                "LANGUAGE": "en_GB",
                "MODE": "hourly",
            }
        ]
    }
    uc = make_voice_uc(scenario, master)

    with patch("adn_server.application.voice_use_cases.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 24, 10, 30)
        uc.scheduled_tts_announcement(0)

    assert uc._tts_running.get(0) is not True
    assert uc._scheduled == []


def test_scheduled_tts_defers_when_same_tg_already_broadcasting() -> None:
    scenario, master = voice_master_scenario()
    voice_tts_config(scenario)
    uc = make_voice_uc(scenario, master)
    uc._broadcast_active_tgs.add("91")

    uc.scheduled_tts_announcement(0)

    assert uc._tts_running.get(0) is not True
    assert len(uc._scheduled) == 1
    delay, (fn, args) = uc._scheduled[0]
    assert delay == 3.0
    assert getattr(fn, "__name__", "") == "scheduled_tts_announcement"
    assert args == (0, 1)


def test_scheduled_tts_sync_exception_clears_running() -> None:
    scenario, master = voice_master_scenario()
    voice_tts_config(scenario)

    class FailingProvider:
        def ensure_tts_ambe(self, config, item, audio_path):
            del config, item, audio_path
            raise OSError("disk full")

        def read_single_file(self, *args):
            return [b"\x00" * 7]

        def pkt_gen(self, *args, **kwargs):
            return iter([])

        def get_ambe_words(self, *args):
            return {}

    scheduled: list[tuple[float, tuple]] = []

    def call_later(delay, fn, *args):
        scheduled.append((delay, (fn, args)))
        return MagicMock()

    uc = VoiceUseCases(
        FailingProvider(),
        scenario.config,
        get_protocols=lambda: {"MASTER-A": master},
        routing_table_for_report=scenario.routing.routing_table_for_report,
        call_later=call_later,
        audio_path="/tmp/audio",
    )

    uc.scheduled_tts_announcement(0)

    assert uc._tts_running[0] is False
