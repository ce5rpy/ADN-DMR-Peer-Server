# ADN DMR Peer Server - tests hbp ingress
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

"""HBP ingress timing and loop control."""

from __future__ import annotations

from tests.harness.assertions import assert_inject_ok
from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    active_routing_table,
    add_openbridge_system,
    patch_routing_wall_time,
)
from tests.harness.scenarios import obp_bridge_scenario

from adn_server.domain import bytes_3, bytes_4


def test_hbp_ingress_sets_rx_start_on_new_stream() -> None:
    """New HBP group stream records RX_START from ingress_pkt_time."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0x12121212)
    t0 = 1_700_000_100.0

    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
        ingress_pkt_time=t0,
    )

    slot_st = scenario.protocols["MASTER-A"].STATUS[2]
    assert slot_st.get("RX_START") == t0
    assert slot_st.get("RX_STREAM_ID") == base.data()[16:20]


def test_hbp_rate_limit_ignores_byte_identical_duplicates() -> None:
    """Compressed duplicate bursts must not inflate the ingress rate counter."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0x90909090)
    t0 = scenario.clock.time()

    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
        ingress_pkt_time=t0,
    )
    for seq in range(1, 25):
        burst = DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4))
        pkt_time = t0 + seq * 0.06
        ok = scenario.inject_hbp("MASTER-A", burst, ingress_pkt_time=pkt_time)
        assert ok is not False
        scenario.inject_hbp("MASTER-A", burst, ingress_pkt_time=pkt_time + 0.003)

    forwarded = len(scenario.capture.for_system("MASTER-B"))
    assert forwarded >= 20


def test_hbp_rate_drop_prevents_bridge_forward() -> None:
    """After ingress RATE DROP, no further packets are bridged."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0x56565656)
    t0 = scenario.clock.time()

    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
        ingress_pkt_time=t0,
    )
    dropped_at: int | None = None
    for seq in range(1, 30):
        ok = scenario.inject_hbp(
            "MASTER-A",
            DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4)),
            ingress_pkt_time=t0 + seq * 0.01,
        )
        if not ok:
            dropped_at = seq
            break
    assert dropped_at is not None

    forwarded_before = len(scenario.capture.for_system("MASTER-B"))
    for seq in range(dropped_at, dropped_at + 10):
        scenario.inject_hbp(
            "MASTER-A",
            DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4)),
            ingress_pkt_time=t0 + seq * 0.01,
        )
    assert len(scenario.capture.for_system("MASTER-B")) == forwarded_before


def test_hbp_same_subscriber_rekey_after_downlink_forwards_to_obp() -> None:
    """Same RF source may start a new stream after downlink (3- vs 4-byte RX_RFS parity)."""
    scenario = obp_bridge_scenario("OBP-CL", tg=7305)
    peer_id = bytes_4(7300392)
    new_stream = 0xFD23D0B3
    slot_st = scenario.protocols["MASTER-A"].STATUS[2]
    slot_st.update(
        {
            "RX_STREAM_ID": bytes_4(158707278),
            "RX_RFS": bytes_4(7300392),
            "RX_PEER": peer_id,
            "RX_TYPE": 2,
            "RX_TIME": scenario.clock.time(),
            "RX_TGID": bytes_3(7305),
        }
    )
    base = PacketSpec(
        peer_id=7300392,
        rf_src=7300392,
        dst_id=7305,
        slot=2,
        stream_id=new_stream,
    )
    n_before = len(scenario.capture.for_system("OBP-CL"))
    ok = scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    assert ok is not False
    assert len(scenario.capture.for_system("OBP-CL")) - n_before == 1


def test_hbp_loop_loser_when_obp_already_has_stream() -> None:
    """Regression: HBP loses loop when OBP already owns stream_id; no bridge forward."""
    bridges = active_routing_table(52090, (("OBP-CL", 1), ("MASTER-A", 2)))
    config = DeterministicScenario().config
    add_openbridge_system(config, "OBP-CL")
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    scenario = DeterministicScenario(config=config, routing_table=bridges)

    stream_id = 0x77778888
    scenario.seed_obp_stream("OBP-CL", stream_id, tgid=52090)

    base = PacketSpec(dst_id=52090, stream_id=stream_id, slot=2)
    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
    )
    ok = scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )
    assert_inject_ok(ok, expected=False)


def test_hbp_obp_reply_reuses_stream_id_after_obp_fin() -> None:
    """After OBP inbound VTERM (_fin), hotspot reply may reuse stream_id without garbled leg."""
    scenario = obp_bridge_scenario("OBP-CL", tg=730444)
    stream = 0xAABBCCDD
    base_obp = PacketSpec(peer_id=73010, rf_src=3340062, dst_id=730444, slot=1, stream_id=stream)
    base_hbp = PacketSpec(peer_id=730002301, rf_src=7300023, dst_id=730444, slot=2, stream_id=stream)

    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base_obp))
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_term_spec(base_obp))
        assert scenario.protocols["OBP-CL"].STATUS[bytes_4(stream)]["_fin"] is True
        n_before = len(scenario.capture.for_system("OBP-CL"))
        for spec in [
            DeterministicScenario.voice_head_spec(base_hbp),
            DeterministicScenario.voice_burst_spec(base_hbp, 1, 1),
            DeterministicScenario.voice_burst_spec(base_hbp, 2, 2),
            DeterministicScenario.voice_term_spec(base_hbp),
        ]:
            scenario.clock.advance(0.06)
            ok = scenario.inject_hbp("MASTER-A", spec)
            assert ok is not False
        assert len(scenario.capture.for_system("OBP-CL")) - n_before == 4
