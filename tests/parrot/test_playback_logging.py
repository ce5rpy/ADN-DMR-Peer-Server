"""Parrot playback logging format."""

from __future__ import annotations

import logging
import re

from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.harness.playback_helpers import FakePlaybackProtocol

from adn_server.application.playback_use_cases import PlaybackUseCases
from adn_server.domain import bytes_3, bytes_4


def test_start_playback_logs_duration_with_two_decimals(caplog) -> None:
    """PLAYBACK duration matches bridge-style %.2f (no float noise in logs)."""
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("PARROT", get_protocol=lambda: proto)
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
