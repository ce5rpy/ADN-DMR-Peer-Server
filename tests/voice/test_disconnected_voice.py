"""Disconnected / linked-to-reflector voice prompts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from tests.harness.voice_helpers import FakeMasterForVoice, FakeVoiceProvider, voice_master_scenario

from adn_server.application.voice_use_cases import VoiceUseCases


class _VoiceMaster(FakeMasterForVoice):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.voice_packets: list[bytes] = []

    def send_voice_packet(self, packet: bytes, _source_id: bytes, _dst_id: bytes, _slot: dict) -> None:
        self.voice_packets.append(packet)


class _WordsProvider(FakeVoiceProvider):
    def get_ambe_words(self, languages: str, audio_path: str) -> dict:
        del audio_path
        silence = b"\x00" * 7
        return {
            languages: {
                "silence": silence,
                "notlinked": silence,
                "linkedto": silence,
                "to": silence,
                **{str(d): silence for d in range(10)},
            }
        }


def _disconnected_uc(master: _VoiceMaster, scenario, provider: FakeVoiceProvider | None = None) -> VoiceUseCases:
    def call_from_reactor(fn, *args):
        fn(*args)

    return VoiceUseCases(
        provider or _WordsProvider(),
        scenario.config,
        get_protocols=lambda: {"MASTER-A": master},
        call_from_reactor=call_from_reactor,
        audio_path="/tmp/audio",
    )


@pytest.mark.behavior
def test_disconnected_voice_not_linked_prompt() -> None:
    """Regression: DEFAULT_REFLECTOR=0 sends not-linked prompt packets."""
    scenario, _ = voice_master_scenario()
    master = _VoiceMaster("MASTER-A")
    master.STATUS[2] = {"RX_TYPE": 2, "TX_TYPE": 2}
    scenario.config["SYSTEMS"]["MASTER-A"]["DEFAULT_REFLECTOR"] = 0
    uc = _disconnected_uc(master, scenario)

    with patch("adn_server.application.voice_use_cases.time") as mock_time:
        mock_time.sleep = MagicMock()
        mock_time.time.side_effect = [2000.0] * 50
        uc.disconnected_voice("MASTER-A")

    assert len(master.voice_packets) >= 1
    assert all(pkt[:4] == b"DMRD" for pkt in master.voice_packets)


@pytest.mark.behavior
def test_disconnected_voice_linked_to_reflector_includes_digits() -> None:
    """Regression: linked reflector prompt builds longer speech sequence than not-linked."""
    scenario, _ = voice_master_scenario()
    master = _VoiceMaster("MASTER-A")
    master.STATUS[2] = {"RX_TYPE": 2, "TX_TYPE": 2}
    scenario.config["SYSTEMS"]["MASTER-A"]["DEFAULT_REFLECTOR"] = 310
    uc = _disconnected_uc(master, scenario)
    linked_say: list[list] = []
    orig_pkt_gen = VoiceUseCases.pkt_gen

    def capture_pkt_gen(self, *args, **kwargs):
        linked_say.append(list(args[4]))
        return orig_pkt_gen(self, *args, **kwargs)

    with patch.object(VoiceUseCases, "pkt_gen", capture_pkt_gen):
        with patch("adn_server.application.voice_use_cases.time") as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.time.side_effect = [3000.0] * 80
            uc.disconnected_voice("MASTER-A")

    assert len(linked_say) == 1
    assert len(linked_say[0]) > 4
    assert len(master.voice_packets) >= 3
    assert all(pkt[:4] == b"DMRD" for pkt in master.voice_packets)


def test_disconnected_voice_skips_when_language_missing() -> None:
    scenario, _ = voice_master_scenario()
    master = _VoiceMaster("MASTER-A")
    master.STATUS[2] = {"RX_TYPE": 2, "TX_TYPE": 2}

    class EmptyWordsProvider(FakeVoiceProvider):
        def get_ambe_words(self, languages: str, audio_path: str) -> dict:
            del languages, audio_path
            return {}

    uc = _disconnected_uc(master, scenario, EmptyWordsProvider())
    uc.disconnected_voice("MASTER-A")

    assert master.voice_packets == []
