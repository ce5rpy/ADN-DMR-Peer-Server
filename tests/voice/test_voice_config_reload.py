"""Voice config reload and announcement LoopingCall management."""

from __future__ import annotations

from unittest.mock import MagicMock

from tests.harness.voice_helpers import FakeVoiceProvider, voice_master_scenario

from adn_server.application.voice_use_cases import VoiceUseCases


def _reload_uc(scenario, *, start_looping_call) -> VoiceUseCases:
    return VoiceUseCases(
        FakeVoiceProvider(),
        scenario.config,
        start_looping_call=start_looping_call,
        audio_path="/tmp/audio",
    )


def test_check_voice_config_reload_starts_enabled_announcement_loop() -> None:
    scenario, _ = voice_master_scenario()
    scenario.config["VOICE"] = {
        "ANNOUNCEMENTS": [
            {
                "ENABLED": True,
                "TG": 91,
                "FILE": "welcome",
                "LANGUAGE": "en_GB",
                "MODE": "interval",
                "INTERVAL": 120,
            }
        ],
    }
    started: list[tuple[float, object]] = []

    def start_looping_call(fn, interval, _now):
        started.append((interval, fn))
        handle = MagicMock(running=True)
        handle.stop = MagicMock()
        return handle

    uc = _reload_uc(scenario, start_looping_call=start_looping_call)
    uc.check_voice_config_reload()

    assert len(started) == 1
    assert started[0][0] == 120.0
    assert 0 in uc._ann_tasks


def test_check_voice_config_reload_stops_removed_announcement() -> None:
    scenario, _ = voice_master_scenario()
    scenario.config["VOICE"] = {"ANNOUNCEMENTS": [{"ENABLED": False, "TG": 91, "FILE": "x"}]}
    stop_mock = MagicMock()
    uc = VoiceUseCases(
        FakeVoiceProvider(),
        scenario.config,
        start_looping_call=lambda *_a: MagicMock(running=True, stop=stop_mock),
        audio_path="/tmp/audio",
    )
    uc._ann_tasks[0] = MagicMock(running=True, stop=stop_mock)

    uc.check_voice_config_reload()

    assert 0 not in uc._ann_tasks
    stop_mock.assert_called_once()


def test_check_voice_config_reload_starts_tts_loop() -> None:
    scenario, _ = voice_master_scenario()
    scenario.config["VOICE"] = {
        "TTS_ANNOUNCEMENTS": [
            {
                "ENABLED": True,
                "TG": 91,
                "FILE": "hourly.ambe",
                "LANGUAGE": "en_GB",
                "MODE": "hourly",
            }
        ],
    }
    started: list[float] = []

    def start_looping_call(_fn, interval, _now):
        started.append(interval)
        return MagicMock(running=True, stop=MagicMock())

    uc = _reload_uc(scenario, start_looping_call=start_looping_call)
    uc.check_voice_config_reload()

    assert started == [30.0]
    assert 0 in uc._tts_tasks
