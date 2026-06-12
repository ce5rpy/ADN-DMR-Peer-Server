# ADN DMR Peer Server - tests parrot recording timers
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

"""Parrot recording idle/max timers and synthetic VTERM."""

from __future__ import annotations

from unittest.mock import patch

from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.harness.playback_helpers import (
    FakePlaybackProtocol,
    install_reactor_capture,
    run_scheduled,
    send_playback,
)

from adn_server.application.playback_use_cases import _RECORD_IDLE_S, PlaybackUseCases


def test_idle_timeout_appends_synthetic_vterm_and_schedules_playback() -> None:
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("ECHO", get_protocol=lambda: proto)
    base = PacketSpec(dst_id=9990, stream_id=0x55555555, slot=2)
    mock_reactor, scheduled = install_reactor_capture()

    with patch("adn_server.application.playback_use_cases.reactor", mock_reactor):
        with patch("adn_server.application.playback_use_cases.time", return_value=200.0):
            send_playback(pb, "ECHO", DeterministicScenario.voice_head_spec(base))
            send_playback(
                pb, "ECHO", DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
            )

        idle_calls = [item for item in scheduled if item[0] == _RECORD_IDLE_S]
        assert idle_calls

        with patch("adn_server.application.playback_use_cases.time", return_value=200.0 + _RECORD_IDLE_S):
            run_scheduled(scheduled, delay=_RECORD_IDLE_S)

    assert not pb._recording_active
    assert pb._playback_busy is True
    assert any(item[0] == 2.0 for item in scheduled)


def test_vterm_commit_does_not_require_synthetic_vterm() -> None:
    pb = PlaybackUseCases("ECHO")
    base = PacketSpec(dst_id=9990, stream_id=0x66666666, slot=2)
    recorded = [
        DeterministicScenario.voice_head_spec(base).data(),
        DeterministicScenario.voice_term_spec(base, seq=2).data(),
    ]

    with_vterm = pb._ensure_vterm(recorded, slot=2)
    assert len(with_vterm) == len(recorded)
    assert pb._packet_is_vterm(with_vterm[-1])
