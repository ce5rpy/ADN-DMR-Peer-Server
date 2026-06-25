"""Parrot re-key and playback packet prep."""

from __future__ import annotations

from unittest.mock import patch

from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.harness.playback_helpers import FakePlaybackProtocol, install_reactor_capture, send_playback

from adn_server.application.playback_use_cases import PlaybackUseCases


def test_recording_rekey_does_not_store_second_vhead() -> None:
    pb = PlaybackUseCases("ECHO", get_protocol=lambda: FakePlaybackProtocol())
    base = PacketSpec(dst_id=9990, stream_id=0x11111111, slot=2)
    rekey = PacketSpec(dst_id=9990, stream_id=0x22222222, slot=2)
    mock_reactor, _scheduled = install_reactor_capture()

    with patch("adn_server.application.playback_use_cases.reactor", mock_reactor):
        with patch("adn_server.application.playback_use_cases.time") as mock_time:
            mock_time.side_effect = [100.0, 100.1, 100.2, 100.3]
            send_playback(pb, "ECHO", DeterministicScenario.voice_head_spec(base))
            send_playback(
                pb, "ECHO", DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
            )
            send_playback(pb, "ECHO", DeterministicScenario.voice_head_spec(rekey))
            send_playback(
                pb, "ECHO", DeterministicScenario.voice_burst_spec(rekey, seq=2, dtype_vseq=2),
            )

    vheads = sum(
        1
        for pkt in pb.CALL_DATA
        if len(pkt) >= 16 and (pkt[15] & 0xF) == 1 and ((pkt[15] & 0x30) >> 4) == 2
    )
    assert vheads == 1
    assert pb._record_stream == rekey.data()[16:20]


def test_prepare_playback_skips_mid_call_vhead_and_renumbers_seq() -> None:
    pb = PlaybackUseCases("ECHO")
    base = PacketSpec(dst_id=9990, stream_id=0x33333333, slot=2)
    rekey = PacketSpec(dst_id=9990, stream_id=0x44444444, slot=2)
    recorded = [
        DeterministicScenario.voice_head_spec(base).data(),
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1).data(),
        DeterministicScenario.voice_head_spec(rekey).data(),
        DeterministicScenario.voice_burst_spec(rekey, seq=2, dtype_vseq=2).data(),
        DeterministicScenario.voice_term_spec(rekey, seq=3).data(),
    ]

    out = pb._prepare_playback_packets(recorded)

    assert len(out) == 4
    assert all(out[i][4] == (i + 1) for i in range(len(out)))
    mid_vheads = sum(
        1
        for pkt in out[1:]
        if len(pkt) >= 16 and (pkt[15] & 0xF) == 1 and ((pkt[15] & 0x30) >> 4) == 2
    )
    assert mid_vheads == 0
    assert out[0][16:20] == out[-1][16:20]
