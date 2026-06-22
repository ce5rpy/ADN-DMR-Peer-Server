# ADN DMR Peer Server - OBP → HBP cross-slot downlink
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations

from adn_server.application.routing.helpers import inject_only_defer_obp_hbp_slot_contention
from adn_server.domain import HBPF_SLT_VHEAD, bytes_3, bytes_4
from tests.harness.deterministic import DeterministicScenario, PacketSpec, patch_routing_wall_time
from tests.harness.scenarios import obp_bridge_scenario


def _two_peer_master(scenario: DeterministicScenario) -> None:
    master = scenario.config["SYSTEMS"]["MASTER-A"]
    master["TS2_STATIC"] = "730444,7144"
    master["PEERS"] = {
        bytes_4(730001): {"CONNECTION": "YES", "OPTIONS": b"TS2=7144;"},
        bytes_4(730002): {"CONNECTION": "YES", "OPTIONS": b"TS1=730444;"},
    }


def test_defer_helper_requires_inject_only_obp_to_master() -> None:
    cfg = {"PROXY": {"TARGET_SYSTEM": "MASTER-A"}, "SYSTEMS": {"MASTER-A": {"MODE": "MASTER"}}}
    sys_cfg = {"MODE": "MASTER", "PEERS": {bytes_4(1): {"CONNECTION": "YES"}}}
    assert inject_only_defer_obp_hbp_slot_contention(
        cfg, "MASTER-A", sys_cfg, source_is_obp=True,
    )
    assert not inject_only_defer_obp_hbp_slot_contention(
        cfg, "MASTER-A", sys_cfg, source_is_obp=False,
    )
    assert not inject_only_defer_obp_hbp_slot_contention(
        {}, "MASTER-A", sys_cfg, source_is_obp=True,
    )


def _seed_busy_slot_2(scenario: DeterministicScenario, peer_id: int) -> None:
    proto = scenario.protocols["MASTER-A"]
    t = scenario.clock.time()
    proto.STATUS[2] = {
        "RX_STREAM_ID": bytes_4(0xAAAAAAAA),
        "RX_PEER": bytes_4(peer_id),
        "RX_TGID": bytes_3(7144),
        "RX_TIME": t,
        "RX_TYPE": HBPF_SLT_VHEAD,
        "TX_STREAM_ID": bytes_4(0xAAAAAAAA),
        "TX_TGID": bytes_3(7144),
        "TX_TIME": t,
        "TX_TYPE": HBPF_SLT_VHEAD,
        "TX_PEER": bytes_4(peer_id),
    }


def test_obp_hbp_forwards_when_bridge_ts_busy_but_peer_listens_other_ts() -> None:
    """OBP bridge leg TS2 must not block downlink to a TS1-static peer (inject-only)."""
    scenario = obp_bridge_scenario("OBP-CL", tg=730444)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    _two_peer_master(scenario)
    _seed_busy_slot_2(scenario, 730001)
    base = PacketSpec(
        peer_id=73010,
        rf_src=3340062,
        dst_id=730444,
        slot=1,
        stream_id=0xBBBBBBBB,
    )
    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    assert len(scenario.capture.for_system("MASTER-A")) > 0


def test_obp_hbp_forwards_dynamic_ua_on_slot_1_when_bridge_ts2_busy() -> None:
    """Dynamic TG keyed on TS1 must receive OBP downlink even when TS2 is occupied."""
    scenario = obp_bridge_scenario("OBP-CL", tg=730444)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    master = scenario.config["SYSTEMS"]["MASTER-A"]
    master["TS2_STATIC"] = "730444,7144"
    p_busy = bytes_4(730001)
    p_dyn = bytes_4(730002)
    master["PEERS"] = {
        p_busy: {"CONNECTION": "YES", "OPTIONS": b"TS2=7144;"},
        p_dyn: {
            "CONNECTION": "YES",
            "OPTIONS": b"TS2=730;SINGLE=1;TIMER=300;",
            "_UA_SESSION": {
                1: {"tgid": 730444, "expires": scenario.clock.time() + 300.0},
            },
        },
    }
    _seed_busy_slot_2(scenario, 730001)
    base = PacketSpec(
        peer_id=73010,
        rf_src=3340062,
        dst_id=730444,
        slot=1,
        stream_id=0xDDDDDDDD,
    )
    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    assert len(scenario.capture.for_system("MASTER-A")) > 0


def test_obp_hbp_single_peer_inject_only_defers_like_repeat() -> None:
    """Sole inject-only hotspot: OBP uses per-peer slot checks (REPEAT parity)."""
    scenario = obp_bridge_scenario("OBP-CL", tg=730444)
    scenario.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    master = scenario.config["SYSTEMS"]["MASTER-A"]
    master["TS2_STATIC"] = "730444,7144"
    master["PEERS"] = {
        bytes_4(730002): {"CONNECTION": "YES", "OPTIONS": b"TS1=730444;"},
    }
    _seed_busy_slot_2(scenario, 730002)
    base = PacketSpec(
        peer_id=73010,
        rf_src=3340062,
        dst_id=730444,
        slot=1,
        stream_id=0xCCCCCCCC,
    )
    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
    assert len(scenario.capture.for_system("MASTER-A")) > 0
