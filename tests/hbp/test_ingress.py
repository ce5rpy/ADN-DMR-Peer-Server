"""HBP ingress timing and loop control."""

from __future__ import annotations

from tests.harness.assertions import assert_inject_ok
from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    active_routing_table,
    add_openbridge_system,
)


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
