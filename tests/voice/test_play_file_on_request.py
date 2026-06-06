"""On-demand AMBE playback (TG 9991-9999, playFileOnRequest)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.harness.voice_helpers import FakeMasterForVoice, FakeVoiceProvider, voice_master_scenario

from adn_server.application.voice_use_cases import VoiceUseCases


class _MasterWithVoice(FakeMasterForVoice):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.voice_packets: list[bytes] = []

    def send_voice_packet(self, packet: bytes, _source_id: bytes, _dst_id: bytes, _slot: dict) -> None:
        self.voice_packets.append(packet)


def _play_file_uc(master: _MasterWithVoice, scenario) -> VoiceUseCases:
    def call_from_reactor(fn, *args):
        fn(*args)

    return VoiceUseCases(
        FakeVoiceProvider(),
        scenario.config,
        get_protocols=lambda: {"MASTER-A": master},
        call_from_reactor=call_from_reactor,
        audio_path="/tmp/audio",
    )


def test_play_file_on_request_sends_all_generated_packets() -> None:
    scenario, _master = voice_master_scenario()
    master = _MasterWithVoice("MASTER-A")
    master.STATUS[2] = {"RX_TYPE": 2, "TX_TYPE": 2}
    uc = _play_file_uc(master, scenario)

    with patch("adn_server.application.voice_use_cases.time") as mock_time:
        mock_time.sleep = MagicMock()
        mock_time.time.side_effect = [1000.0] * 20
        uc.play_file_on_request("9991", "MASTER-A")

    assert len(master.voice_packets) == 3
    assert all(pkt[:4] == b"DMRD" for pkt in master.voice_packets)


def test_play_file_on_request_skips_when_file_missing() -> None:
    scenario, _master = voice_master_scenario()
    master = _MasterWithVoice("MASTER-A")
    master.STATUS[2] = {}

    class EmptyProvider(FakeVoiceProvider):
        def read_single_file(self, audio_path: str, lang: str, file_number: str) -> list:
            del audio_path, lang, file_number
            return []

    def call_from_reactor(fn, *args):
        fn(*args)

    uc = VoiceUseCases(
        EmptyProvider(),
        scenario.config,
        get_protocols=lambda: {"MASTER-A": master},
        call_from_reactor=call_from_reactor,
        audio_path="/tmp/audio",
    )

    uc.play_file_on_request("9992", "MASTER-A")

    assert master.voice_packets == []


def test_play_file_on_request_requires_reactor_callback() -> None:
    scenario, _master = voice_master_scenario()
    master = _MasterWithVoice("MASTER-A")
    master.STATUS[2] = {}
    uc = VoiceUseCases(
        FakeVoiceProvider(),
        scenario.config,
        get_protocols=lambda: {"MASTER-A": master},
        audio_path="/tmp/audio",
    )

    uc.play_file_on_request("9993", "MASTER-A")

    assert master.voice_packets == []
