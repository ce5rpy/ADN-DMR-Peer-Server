# ADN DMR Peer Server - tests harness voice helpers
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

"""Shared fakes for VoiceUseCases tests."""

from __future__ import annotations

from typing import Any, Iterator

from adn_server.application.routing.announcement_ptt_inject import (
    announcement_ptt_system,
    inject_announcement_ptt,
)
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
        stream_id = bytes_4(0xA0A0A0A0)
        for seq in range(3):
            yield b"DMRD" + bytes([seq]) + rf_src[:3] + dst_id[:3] + peer[:4] + bytes([ts_bit | 0x10]) + stream_id + b"\x00" * 33 + b"\x00\x00"

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
    config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    config["SYSTEMS"]["MASTER-A"]["PEERS"] = {
        "1001": {"CALLSIGN": "TEST", "IP": "127.0.0.1", "PORT": 62032},
    }
    bridges = active_routing_table(tg, (("MASTER-A", 2), ("MASTER-B", 2)))
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
    ptt_system = announcement_ptt_system(scenario.config)
    server_id = scenario.config.get("GLOBAL", {}).get("SERVER_ID", bytes_4(9990))
    if not isinstance(server_id, bytes):
        server_id = bytes_4(int(server_id or 0) & 0xFFFFFFFF)

    def call_later(delay, fn, *args):
        scheduled.append((delay, (fn, args)))
        return type("H", (), {"active": lambda self: True, "cancel": lambda self: None})()

    def inject_announcement_ptt_cb(pkt: bytes, pkt_time: float) -> bool | None:
        if not ptt_system:
            return False
        accepted = inject_announcement_ptt(
            scenario.routing,
            ptt_system,
            pkt,
            pkt_time=pkt_time,
            server_id=server_id,
        )
        if hasattr(master, "send_system"):
            master.send_system(pkt)
        return accepted

    uc = VoiceUseCases(
        FakeVoiceProvider(),
        scenario.config,
        get_protocols=lambda: {"MASTER-A": master, **{k: v for k, v in scenario.protocols.items() if k != "MASTER-A"}},
        routing_table_for_report=scenario.routing.routing_table_for_report,
        call_later=call_later,
        audio_path=audio_path,
        inject_announcement_ptt=inject_announcement_ptt_cb,
    )
    uc._announcement_ptt_system = ptt_system
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
