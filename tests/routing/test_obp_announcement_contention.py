# ADN DMR Peer Server - OBP vs server announcement slot contention
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations

from tests.harness.deterministic import DeterministicScenario, PacketSpec, patch_routing_wall_time
from tests.harness.scenarios import obp_bridge_scenario

from adn_server.domain import HBPF_SLT_VHEAD, HBPF_SLT_VTERM, bytes_3, bytes_4


def _seed_server_broadcast_slot(scenario: DeterministicScenario, *, ann_tg: int = 91) -> None:
    proto = scenario.protocols["MASTER-A"]
    t = scenario.clock.time()
    proto.STATUS[2] = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_TIME": t,
        "TX_RFS": bytes_3(5000),
        "TX_TGID": bytes_3(ann_tg),
        "TX_STREAM_ID": bytes_4(0xA0A0A0A0),
    }


def test_obp_blocked_while_server_broadcast_holds_master_ts2() -> None:
    """Legacy parity: OBP must not route onto TS2 while announcement holds TX row."""
    scenario = obp_bridge_scenario("OBP-CL", tg=7144)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    scenario.config["SYSTEMS"]["MASTER-A"]["PEERS"] = {
        bytes_4(730002): {"CONNECTION": "YES", "OPTIONS": b"TS2=7144;"},
    }
    _seed_server_broadcast_slot(scenario, ann_tg=91)
    base = PacketSpec(
        peer_id=73010,
        rf_src=3340062,
        dst_id=7144,
        slot=1,
        stream_id=0x11111111,
    )
    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    assert scenario.capture.for_system("MASTER-A") == []


def test_obp_still_forwards_when_no_server_broadcast_hold() -> None:
    """Inject-only defer remains when the slot is not held by server voice."""
    scenario = obp_bridge_scenario("OBP-CL", tg=7144)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    scenario.config["SYSTEMS"]["MASTER-A"]["PEERS"] = {
        bytes_4(730002): {"CONNECTION": "YES", "OPTIONS": b"TS2=7144;"},
    }
    proto = scenario.protocols["MASTER-A"]
    t = scenario.clock.time()
    proto.STATUS[2] = {
        "RX_TYPE": HBPF_SLT_VTERM,
        "TX_TYPE": HBPF_SLT_VTERM,
        "TX_TIME": t - 60.0,
        "TX_RFS": bytes_3(3340062),
        "TX_TGID": bytes_3(7144),
    }
    base = PacketSpec(
        peer_id=73010,
        rf_src=3340062,
        dst_id=7144,
        slot=1,
        stream_id=0x22222222,
    )
    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    assert len(scenario.capture.for_system("MASTER-A")) > 0
