"""HBP ingress rate limit."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_capture_unchanged
from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_routing_table

import adn_server.application.routing_use_cases as buc


@pytest.mark.behavior
def test_hbp_rate_limit_drops_excessive_ingress_rate() -> None:
    """Regression: excessive ingress rate triggers drop; post-drop forwards stall."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0x55667788)
    t0 = scenario.clock.time()

    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
        ingress_pkt_time=t0,
    )
    dropped = False
    dropped_at = 0
    for seq in range(1, 30):
        ok = scenario.inject_hbp(
            "MASTER-A",
            DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4)),
            ingress_pkt_time=t0 + seq * 0.01,
        )
        if not ok:
            dropped = True
            dropped_at = seq
            break
    assert dropped

    forwarded_before = len(scenario.capture.for_system("MASTER-B"))
    for seq in range(dropped_at, dropped_at + 5):
        scenario.inject_hbp(
            "MASTER-A",
            DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4)),
            ingress_pkt_time=t0 + seq * 0.01,
        )
    assert_capture_unchanged(scenario, "MASTER-B", forwarded_before)


def test_hbp_rate_limit_uses_ingress_time_not_wall_clock() -> None:
    """Rate control must use ingress_pkt_time even when wall clock is frozen."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0x34343434)
    t0 = 1_700_000_200.0

    original_time = buc.time.time
    buc.time.time = lambda: t0
    try:
        scenario.inject_hbp(
            "MASTER-A",
            DeterministicScenario.voice_head_spec(base),
            ingress_pkt_time=t0,
        )
        accepted = 0
        for seq in range(1, 24):
            ok = scenario.inject_hbp(
                "MASTER-A",
                DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=min(seq, 4)),
                ingress_pkt_time=t0 + seq * 0.06,
            )
            if ok is not False:
                accepted += 1
        assert accepted >= 20
    finally:
        buc.time.time = original_time
