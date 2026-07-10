# ADN DMR Peer Server - tests echo rekey playback
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

"""Parrot re-key and playback packet prep."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.harness.playback_helpers import (
    FakePlaybackProtocol,
    make_capture_call_later,
    noop_call_later,
    send_playback,
)

from adn_server.application.playback_use_cases import PlaybackUseCases
from adn_server.domain import bytes_4


def _long_voice_recording(
    base: PacketSpec,
    *,
    burst_count: int,
) -> list[bytes]:
    """Simulate MMDVM seq byte wrapping (1..255, 0, 1..) over a long QSO."""
    recorded = [DeterministicScenario.voice_head_spec(base).data()]
    for i in range(1, burst_count + 1):
        recorded.append(
            DeterministicScenario.voice_burst_spec(
                base,
                seq=i & 0xFF,
                dtype_vseq=((i - 1) % 4) + 1,
            ).data()
        )
    recorded.append(DeterministicScenario.voice_term_spec(base, seq=(burst_count + 1) & 0xFF).data())
    return recorded


@pytest.mark.behavior
def test_prepare_playback_preserves_source_seq_past_255_packets() -> None:
    """Regression: long QSO keeps source seq; new stream segment when seq byte wraps."""
    pb = PlaybackUseCases("ECHO", call_later=noop_call_later)
    base = PacketSpec(dst_id=9990, stream_id=0x55555555, slot=2)
    recorded = _long_voice_recording(base, burst_count=500)
    pb._playback_stream_id = bytes_4(0x77777777)

    out = pb._prepare_playback_packets(recorded)

    assert len(out) == len(recorded) + 1  # synthetic VHEAD at seq wrap
    assert len({p[16:20] for p in out}) >= 2

    def seq_trace(packets: list[bytes], *, skip_mid_vhead: bool) -> list[int]:
        trace: list[int] = []
        for i, pkt in enumerate(packets):
            if skip_mid_vhead and i > 0 and pb._packet_is_vhead(pkt):
                continue
            trace.append(pkt[4])
        return trace

    rec_seqs = seq_trace(recorded, skip_mid_vhead=True)
    out_seqs = seq_trace(out, skip_mid_vhead=False)
    wrap_at = next(i for i in range(1, len(rec_seqs)) if rec_seqs[i] < rec_seqs[i - 1])
    assert out_seqs == rec_seqs[: wrap_at + 1] + [rec_seqs[0]] + rec_seqs[wrap_at + 1 :]
    assert recorded[256][4] == 0


@pytest.mark.behavior
def test_start_playback_sends_preserved_seq_over_30s_recording() -> None:
    """End-to-end: ~500 bursts @ 60ms ≈ 30s; replay seq on wire must match recording."""
    proto = FakePlaybackProtocol()
    call_later, scheduled = make_capture_call_later()
    pb = PlaybackUseCases("ECHO", call_later=call_later, get_protocol=lambda: proto)
    base = PacketSpec(dst_id=9990, stream_id=0x66666666, slot=2)
    burst_count = 500
    recorded = _long_voice_recording(base, burst_count=burst_count)

    pb._playback_stream_id = bytes_4(0x77777777)
    out = pb._prepare_playback_packets(recorded)
    assert len(out) == len(recorded) + 1

    pb._playback_packets = out
    pb._playback_index = 0
    pb._playback_busy = True
    pb._send_next_packet(proto)
    while scheduled:
        _delay, fn, args = scheduled.pop(0)
        fn(*args)

    assert len(proto.sent) == len(out)


def test_recording_rekey_does_not_store_second_vhead() -> None:
    call_later, _scheduled = make_capture_call_later()
    pb = PlaybackUseCases(
        "ECHO",
        call_later=call_later,
        get_protocol=lambda: FakePlaybackProtocol(),
    )
    base = PacketSpec(dst_id=9990, stream_id=0x11111111, slot=2)
    rekey = PacketSpec(dst_id=9990, stream_id=0x22222222, slot=2)

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


def test_prepare_playback_skips_mid_call_vhead_and_preserves_seq() -> None:
    pb = PlaybackUseCases("ECHO", call_later=noop_call_later)
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
    # Mid-call VHEAD (recorded[2]) dropped; source seq preserved (legacy playback.py).
    assert out[0][4] == recorded[0][4]
    assert out[1][4] == recorded[1][4]
    assert out[2][4] == recorded[3][4]
    assert out[3][4] == recorded[4][4]
    mid_vheads = sum(
        1
        for pkt in out[1:]
        if len(pkt) >= 16 and (pkt[15] & 0xF) == 1 and ((pkt[15] & 0x30) >> 4) == 2
    )
    assert mid_vheads == 0
    assert out[0][16:20] == out[-1][16:20]
