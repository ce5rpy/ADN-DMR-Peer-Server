"""Shared fakes for VoiceUseCases tests."""

from __future__ import annotations

from typing import Any, Iterator

from adn_server.application.voice_use_cases import VoiceUseCases
from adn_server.domain import bytes_3, bytes_4
from tests.harness.deterministic import DeterministicScenario, FakeHbpProtocol, active_routing_table


class FakeVoiceProvider:
    def get_ambe_words(self, languages: str, audio_path: str) -> dict[str, dict[str, Any]]:
        return {languages: {"silence": b"\x00" * 7}}

    def pkt_gen(
        self,
        rf_src: bytes,
        dst_id: bytes,
        peer: bytes,
        slot: int,
        phrase: list[Any],
    ) -> Iterator[bytes]:
        del phrase
        ts_bit = 0x80 if slot else 0
        for seq in range(3):
            yield b"DMRD" + bytes([seq]) + rf_src[:3] + dst_id[:3] + peer[:4] + bytes([ts_bit | 0x10]) + bytes_4(0xA0A0A0A0 + seq) + b"\x00" * 33 + b"\x00\x00"

    def read_single_file(self, audio_path: str, lang: str, file_number: str) -> list:
        del audio_path, lang, file_number
        return [b"\x00" * 7]

    def ensure_tts_ambe(self, config: dict, item: dict, audio_path: str) -> str | None:
        del config, item, audio_path
        return "/tmp/fake.ambe"


class FakeMasterForVoice(FakeHbpProtocol):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._system = name
        self.sent: list[bytes] = []

    def send_system(self, packet: bytes) -> None:
        self.sent.append(packet)


def voice_master_scenario(tg: int = 91) -> tuple[DeterministicScenario, FakeMasterForVoice]:
    config = DeterministicScenario().config
    master = FakeMasterForVoice("MASTER-A")
    config["SYSTEMS"]["MASTER-A"]["PEERS"] = {
        "1001": {"CALLSIGN": "TEST", "IP": "127.0.0.1", "PORT": 62032},
    }
    bridges = active_routing_table(tg, (("MASTER-A", 2),))
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    scenario.protocols["MASTER-A"] = master
    master.STATUS[2] = {
        "RX_TYPE": 2,
        "TX_TYPE": 2,
        "RX_STREAM_ID": b"\x00" * 4,
    }
    return scenario, master


def reflector_routing_entry(system: str = "MASTER-A", reflector: int = 310) -> dict[str, list[dict[str, Any]]]:
    return {
        "#{}".format(reflector): [
            {
                "SYSTEM": system,
                "TS": 2,
                "TGID": bytes_3(9),
                "ACTIVE": True,
                "TIMEOUT": 600,
                "TO_TYPE": "ON",
                "ON": [bytes_3(reflector)],
                "OFF": [],
                "RESET": [],
                "TIMER": 1000.0,
            }
        ]
    }


def make_voice_uc(
    scenario: DeterministicScenario,
    master: FakeMasterForVoice,
    *,
    audio_path: str = "/tmp/audio",
) -> VoiceUseCases:
    scheduled: list[tuple[float, tuple]] = []

    def call_later(delay, fn, *args):
        scheduled.append((delay, (fn, args)))
        return type("H", (), {"active": lambda self: True, "cancel": lambda self: None})()

    uc = VoiceUseCases(
        FakeVoiceProvider(),
        scenario.config,
        get_protocols=lambda: {"MASTER-A": master},
        routing_table_for_report=scenario.routing.routing_table_for_report,
        call_later=call_later,
        audio_path=audio_path,
    )
    uc._scheduled = scheduled
    return uc


def drain_call_later(uc: VoiceUseCases, max_rounds: int = 200) -> None:
    scheduled = getattr(uc, "_scheduled", None)
    if scheduled is None:
        return
    for _ in range(max_rounds):
        if not scheduled:
            break
        _, (fn, args) = scheduled.pop(0)
        fn(*args)


def voice_announcement_config(
    scenario: DeterministicScenario,
    *,
    tg: int = 91,
    enabled: bool = True,
    file_number: str = "test-msg",
) -> None:
    scenario.config["VOICE"] = {
        "ANNOUNCEMENTS": [
            {
                "ENABLED": enabled,
                "TG": tg,
                "FILE": file_number,
                "LANGUAGE": "en_GB",
                "MODE": "interval",
            }
        ]
    }


def voice_tts_config(
    scenario: DeterministicScenario,
    *,
    tg: int = 91,
    enabled: bool = True,
    file_number: str = "tts-msg.ambe",
) -> None:
    scenario.config["VOICE"] = {
        "TTS_ANNOUNCEMENTS": [
            {
                "ENABLED": enabled,
                "TG": tg,
                "FILE": file_number,
                "LANGUAGE": "en_GB",
                "MODE": "interval",
            }
        ]
    }
