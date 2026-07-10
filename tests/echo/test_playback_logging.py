# ADN DMR Peer Server - tests echo playback logging
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

"""Parrot playback logging format."""

from __future__ import annotations

import logging
import re

from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.harness.playback_helpers import FakePlaybackProtocol, noop_call_later

from adn_server.application.playback_use_cases import PlaybackUseCases
from adn_server.domain import bytes_3, bytes_4


def test_start_playback_logs_duration_with_two_decimals(caplog) -> None:
    """PLAYBACK duration matches bridge-style %.2f (no float noise in logs)."""
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("ECHO", call_later=noop_call_later, get_protocol=lambda: proto)
    base = PacketSpec(dst_id=9990, stream_id=0x88888888, slot=2)
    recorded = [DeterministicScenario.voice_head_spec(base).data()]

    with caplog.at_level(logging.INFO, logger="adn_server.application.playback_use_cases"):
        pb._start_playback(
            proto,
            recorded,
            bytes_3(base.rf_src),
            bytes_4(base.peer_id),
            bytes_3(base.dst_id),
            2,
            10.985645771026611,
        )

    playback_lines = [r.message for r in caplog.records if "*START  PLAYBACK*" in r.message]
    assert len(playback_lines) == 1
    assert re.search(r"Duration: 10\.99\b", playback_lines[0])
    assert "10.985645771026611" not in playback_lines[0]
