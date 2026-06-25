"""Parrot playback send loop and max recording timer."""

from __future__ import annotations

import logging
import re
from unittest.mock import patch

from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.harness.playback_helpers import (
    FakePlaybackProtocol,
    install_reactor_capture,
    run_scheduled,
    send_playback,
)

from adn_server.application.playback_use_cases import (
    _PACKET_INTERVAL_S,
    _PLAYBACK_DELAY_S,
    _RECORD_IDLE_S,
    _SOURCE_MAX_S,
    PlaybackUseCases,
)
from adn_server.domain import bytes_3, bytes_4


def test_send_next_packet_emits_all_packets_then_finishes() -> None:
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("ECHO", get_protocol=lambda: proto)
    pb._playback_busy = True
    pb._playback_stream_id = bytes_4(0x77777777)
    pb._playback_packets = [bytes([i]) * 55 for i in range(1, 5)]
    pb._playback_index = 0
    mock_reactor, scheduled = install_reactor_capture()

    with patch("adn_server.application.playback_use_cases.reactor", mock_reactor):
        pb._send_next_packet(proto)
        while scheduled:
            run_scheduled(scheduled)

    assert len(proto.sent) == 4
    assert pb._playback_busy is False
    assert pb._playback_packets == []
    assert pb._playback_index == 0


def test_start_playback_sends_first_packet_and_schedules_rest() -> None:
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("ECHO", get_protocol=lambda: proto)
    base = PacketSpec(dst_id=9990, stream_id=0x88888888, slot=2)
    recorded = [
        DeterministicScenario.voice_head_spec(base).data(),
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1).data(),
    ]
    mock_reactor, scheduled = install_reactor_capture()

    with patch("adn_server.application.playback_use_cases.reactor", mock_reactor):
        pb._start_playback(
            proto,
            recorded,
            bytes_3(base.rf_src),
            bytes_4(base.peer_id),
            bytes_3(base.dst_id),
            2,
            1.5,
        )

    assert len(proto.sent) == 1
    assert pb._playback_index == 1
    assert any(item[0] == _PACKET_INTERVAL_S for item in scheduled)
    with patch("adn_server.application.playback_use_cases.reactor", mock_reactor):
        while scheduled:
            run_scheduled(scheduled)

    assert len(proto.sent) == 2
    assert pb._playback_busy is False


def test_max_duration_commits_recording_when_no_vterm() -> None:
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("ECHO", get_protocol=lambda: proto)
    base = PacketSpec(dst_id=9990, stream_id=0x99999999, slot=2)
    pb._recording_active = True
    pb.CALL_DATA = [DeterministicScenario.voice_head_spec(base).data()]
    pb._record_stream = base.data()[16:20]
    pb.STATUS["RX_START"] = 100.0
    pb._record_ctx = {
        "slot": 2,
        "rf_src": bytes_3(base.rf_src),
        "peer_id": bytes_4(base.peer_id),
        "dst_id": bytes_3(base.dst_id),
    }
    mock_reactor, scheduled = install_reactor_capture()

    with patch("adn_server.application.playback_use_cases.reactor", mock_reactor):
        with patch("adn_server.application.playback_use_cases.time", return_value=100.0 + _SOURCE_MAX_S):
            pb._on_record_max_duration(proto)

    assert not pb._recording_active
    assert pb._playback_busy is True
    assert any(item[0] == _PLAYBACK_DELAY_S for item in scheduled)


def test_packet_interval_matches_expected() -> None:
    proto = FakePlaybackProtocol()
    pb = PlaybackUseCases("ECHO", get_protocol=lambda: proto)
    pb._playback_busy = True
    pb._playback_stream_id = bytes_4(0xAAAAAAAA)
    pb._playback_packets = [b"\x01" * 55, b"\x02" * 55]
    pb._playback_index = 0
    mock_reactor, scheduled = install_reactor_capture()

    with patch("adn_server.application.playback_use_cases.reactor", mock_reactor):
        pb._send_next_packet(proto)

    assert scheduled[0][0] == _PACKET_INTERVAL_S


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

