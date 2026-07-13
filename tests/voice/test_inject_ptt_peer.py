# ADN DMR Peer Server - tests voice inject PTT peer resolution
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

"""Synthetic announcement PTT uses SERVER_ID, not a hotspot peer id."""

from __future__ import annotations

from tests.harness.scenarios import obp_bridge_scenario
from tests.harness.voice_helpers import FakeMasterForVoice, make_voice_uc

from adn_server.domain import bytes_3, bytes_4, int_id


def test_inject_packet_peer_is_always_server_id() -> None:
    scenario = obp_bridge_scenario("OBP-CL", tg=730600)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    peer = bytes_4(730039210)
    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    sys_cfg["PEERS"] = {peer: {"CONNECTION": "YES", "OPTIONS": b"TS2=730500;SINGLE=1;"}}
    pk = bytes_4(730039210)
    sys_cfg.setdefault("_PEER_UA_MULTI_TGS", {}).setdefault(pk, {})[2] = {730600}
    master = FakeMasterForVoice("MASTER-A")
    master.STATUS[2] = {"RX_TYPE": 2, "TX_TYPE": 2, "RX_STREAM_ID": b"\x00" * 4}
    scenario.protocols["MASTER-A"] = master
    uc = make_voice_uc(scenario, master)
    targets = [{"ts": 2}]

    peer_field = uc._announcement_packet_peer(730600, targets, bytes_4(730039101))

    assert int_id(peer_field) == int_id(uc._global_server_id_bytes())
    assert int_id(peer_field) != 730039210
    assert int_id(peer_field) != 730039101


def test_inject_emits_master_tx_voice_events_for_monitor() -> None:
    scenario = obp_bridge_scenario("OBP-CL", tg=730600)
    master = FakeMasterForVoice("MASTER-A")
    uc = make_voice_uc(scenario, master)
    events: list[str] = []
    uc._send_routing_event = events.append  # type: ignore[method-assign]
    stream_id = b"\xab\xcd\xef\x01"
    rf_src = bytes_3(1000001)
    pkts_by_ts = {
        2: [
            b"DMRD" + b"\x00" * 1 + rf_src + bytes_3(730600) + b"\x00" * 3 + b"\x80" + stream_id,
        ],
    }
    targets = [{"name": "MASTER-A", "ts": 2, "slot": master.STATUS[2]}]

    uc._maybe_begin_legacy_voice_report(targets, pkts_by_ts, 730600)

    assert len(events) == 1
    assert events[0].startswith("GROUP VOICE,START,TX,MASTER-A,")
    assert ",2,730600" in events[0]
    assert uc._voice_report_state is not None


def test_inject_ptt_prefers_dynamic_ua_slot() -> None:
    scenario = obp_bridge_scenario("OBP-CL", tg=730600)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    peer = bytes_4(730039210)
    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    sys_cfg["PEERS"] = {peer: {"CONNECTION": "YES", "OPTIONS": b"TS2=730500;"}}
    pk = bytes_4(730039210)
    sys_cfg.setdefault("_PEER_UA_MULTI_TGS", {}).setdefault(pk, {})[2] = {730600}
    master = FakeMasterForVoice("MASTER-A")
    master.STATUS[2] = {
        "RX_TYPE": 1,
        "TX_TYPE": 1,
        "RX_TGID": bytes_3(730600),
        "TX_TGID": bytes_3(730600),
        "RX_STREAM_ID": b"\x01" * 4,
    }
    master.STATUS[1] = {"RX_TYPE": 2, "TX_TYPE": 2, "RX_STREAM_ID": b"\x00" * 4}
    scenario.protocols["MASTER-A"] = master
    uc = make_voice_uc(scenario, master)

    targets, busy = uc._build_inject_ptt_targets("TTS-2", 730600)

    assert busy == 0
    assert len(targets) == 1
    assert targets[0]["ts"] == 2


def test_inject_ptt_prefers_active_bridge_slot_for_static_tg() -> None:
    scenario = obp_bridge_scenario("OBP-CL", tg=730500)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    peer = bytes_4(730039210)
    sys_cfg = scenario.config["SYSTEMS"]["MASTER-A"]
    sys_cfg["PEERS"] = {peer: {"CONNECTION": "YES", "OPTIONS": b"TS2=730500;"}}
    master = FakeMasterForVoice("MASTER-A")
    master.STATUS[2] = {
        "RX_TYPE": 1,
        "TX_TYPE": 1,
        "TX_TGID": bytes_3(730500),
        "RX_STREAM_ID": b"\x01" * 4,
    }
    master.STATUS[1] = {"RX_TYPE": 2, "TX_TYPE": 2, "RX_STREAM_ID": b"\x00" * 4}
    scenario.protocols["MASTER-A"] = master
    uc = make_voice_uc(scenario, master)

    targets, busy = uc._build_inject_ptt_targets("TTS-1", 730500)

    assert busy == 0
    assert targets[0]["ts"] == 2
