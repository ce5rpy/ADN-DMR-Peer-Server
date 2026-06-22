# ADN DMR Peer Server - bridge slot contention behaviour
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations

import time

import pytest

from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD, HBPF_SLT_VTERM
from tests.harness.deterministic import DeterministicScenario, PacketSpec, minimal_config
from tests.support.hbp_repeat_stack import build_hbp_repeat_stack

pytestmark = pytest.mark.behavior

_TG_A = 7144
_TG_B = 730444


def _bridge_leg(sys: str, tg: int) -> dict:
    return {
        "SYSTEM": sys,
        "TS": 2,
        "TGID": tg,
        "ACTIVE": True,
        "TIMEOUT": 0,
        "TO_TYPE": "OFF",
    }


def _bridge_table() -> dict:
    return {
        str(_TG_A): [_bridge_leg("HOTSPOT", _TG_A), _bridge_leg("NETWORK", _TG_A)],
        str(_TG_B): [_bridge_leg("HOTSPOT", _TG_B), _bridge_leg("NETWORK", _TG_B)],
    }


def test_bridge_blocks_second_tg_on_busy_slot_with_zero_hangtime() -> None:
    config = minimal_config(("HOTSPOT", "NETWORK"))
    config["SYSTEMS"]["HOTSPOT"]["GROUP_HANGTIME"] = 0
    config["SYSTEMS"]["NETWORK"]["GROUP_HANGTIME"] = 0
    scenario = DeterministicScenario(config, _bridge_table())
    scenario.protocols["HOTSPOT"].STATUS[2] = {
        "RX_TYPE": HBPF_SLT_VHEAD,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": bytes_3(_TG_A),
        "RX_TIME": scenario.clock.time(),
        "RX_STREAM_ID": bytes_4(0xAAAAAAAA),
        "RX_RFS": bytes_3(7300444),
        "RX_PEER": bytes_4(730001),
    }
    spec = PacketSpec(
        rf_src=3120001,
        dst_id=_TG_B,
        slot=2,
        stream_id=0xBBBBBBBB,
        payload=b"\x00" * 33,
    )
    scenario.inject_hbp("NETWORK", DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1))
    assert scenario.capture.for_system("HOTSPOT") == []


def test_send_peer_blocks_downlink_on_busy_slot() -> None:
    stack = build_hbp_repeat_stack(talker_alias=False, system_name="MASTER-A")
    peer = bytes_4(730002)
    addr = ("10.0.0.31", 62031)
    stack.register_peer(peer, addr, options=f"TS2={_TG_A},{_TG_B};")
    stack.hbp.STATUS[2] = {
        "RX_TYPE": HBPF_SLT_VHEAD,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": bytes_3(_TG_A),
        "RX_TIME": time.time(),
        "RX_STREAM_ID": bytes_4(0xCCCCCCCC),
    }
    spec = PacketSpec(dst_id=_TG_B, slot=2, stream_id=0xDDDDDDDD, payload=b"\x00" * 33)
    pkt = DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1).data()
    stack.hbp.send_peer(peer, pkt)
    assert stack.transport.for_addr(addr) == []


def test_group_hangtime_blocks_after_vterm() -> None:
    config = minimal_config(("HOTSPOT", "NETWORK"))
    config["SYSTEMS"]["HOTSPOT"]["GROUP_HANGTIME"] = 30
    scenario = DeterministicScenario(config, _bridge_table())
    now = scenario.clock.time()
    scenario.protocols["HOTSPOT"].STATUS[2] = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "RX_TGID": bytes_3(_TG_A),
        "RX_TIME": now,
        "TX_TGID": bytes_3(_TG_A),
        "TX_TIME": now,
    }
    spec = PacketSpec(rf_src=3120001, dst_id=_TG_B, slot=2, stream_id=0xEEEEEEEE, payload=b"\x00" * 33)
    scenario.inject_hbp("NETWORK", DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1))
    assert scenario.capture.for_system("HOTSPOT") == []
