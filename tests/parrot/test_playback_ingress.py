"""Parrot ingress path (PEER dmrd_received + record-to-playback)."""

from __future__ import annotations

import logging
from unittest.mock import patch

from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.harness.playback_helpers import FakePlaybackProtocol, install_reactor_capture, send_playback

from adn_server.application.playback_use_cases import _PLAYBACK_DELAY_S, _RECORD_IDLE_S, PlaybackUseCases


def test_dmrd_received_accepts_ingress_pkt_time_kwarg() -> None:
    """Regression: PEER udp_hbp passes ingress_pkt_time (parrot must not TypeError)."""
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("PARROT", get_protocol=lambda: proto)
    base = PacketSpec(dst_id=9990, stream_id=0x12121212, slot=2)
    args = DeterministicScenario.voice_head_spec(base).decoded_hbp_args()

    pb.dmrd_received(
        "PARROT",
        args["peer_id"],
        args["rf_src"],
        args["dst_id"],
        args["seq"],
        args["slot"],
        args["call_type"],
        args["frame_type"],
        args["dtype_vseq"],
        args["stream_id"],
        DeterministicScenario.voice_head_spec(base).data(),
        ingress_pkt_time=1_700_000_000.0,
    )

    assert pb._recording_active is True
    assert len(pb.CALL_DATA) == 1


def test_ingress_pkt_time_enables_record_to_playback(caplog) -> None:
    """Regression: PEER path (ingress_pkt_time) records voice and schedules playback."""
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("PARROT", get_protocol=lambda: proto)
    base = PacketSpec(dst_id=9990, stream_id=0x34343434, slot=2)
    mock_reactor, scheduled = install_reactor_capture()
    t0 = 1_700_000_000.0

    with patch("adn_server.application.playback_use_cases.reactor", mock_reactor):
        with patch("adn_server.application.playback_use_cases.time", return_value=t0):
            send_playback(pb, "PARROT", DeterministicScenario.voice_head_spec(base))
            send_playback(
                pb,
                "PARROT",
                DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
                ingress_pkt_time=t0 + 2.0,
            )
        with patch("adn_server.application.playback_use_cases.time", return_value=t0 + _RECORD_IDLE_S + 1):
            with caplog.at_level(logging.INFO, logger="adn_server.application.playback_use_cases"):
                pb._on_record_idle(proto)

    assert any(item[0] == _PLAYBACK_DELAY_S for item in scheduled)
    assert pb._playback_busy is True
    assert any("*END   RECORDING*" in r.message for r in caplog.records)
    assert not any("unexpected keyword argument" in r.message for r in caplog.records)
