"""HBP ingress 180s timeout and stream collision."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_forwarded, assert_inject_ok
from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_routing_table

from adn_server.domain import bytes_3, bytes_4
from adn_server.domain.hbp_protocol import HBPF_SLT_VHEAD


def test_hbp_source_timeout_drops_after_180_seconds() -> None:
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0x90909090)
    t0 = scenario.clock.time()

    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
        ingress_pkt_time=t0,
    )
    ok = scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
        ingress_pkt_time=t0 + 181.0,
    )

    assert not ok
    assert scenario.protocols["MASTER-A"].STATUS[2].get("LOOPLOG") is True


def test_hbp_stream_collision_drops_conflicting_new_stream() -> None:
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    t0 = scenario.clock.time()
    slot = scenario.protocols["MASTER-A"].STATUS[2]
    slot.update(
        {
            "RX_STREAM_ID": bytes_4(0x80808080),
            "RX_TYPE": HBPF_SLT_VHEAD,
            "RX_RFS": bytes_3(1111111),
            "RX_TGID": bytes_3(91),
            "RX_TIME": t0,
            "RX_START": t0,
        }
    )
    base = PacketSpec(dst_id=91, stream_id=0x70707070, rf_src=2222222)

    ok = scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
        ingress_pkt_time=t0 + 0.1,
    )

    assert not ok
    assert len(scenario.capture.for_system("MASTER-B")) == 0


@pytest.mark.behavior
def test_hbp_collision_allows_same_subscriber_rekey() -> None:
    """Regression: same RF source may start a new stream while prior call is still open."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    t0 = scenario.clock.time()
    rf_src = 3120001
    slot = scenario.protocols["MASTER-A"].STATUS[2]
    slot.update(
        {
            "RX_STREAM_ID": bytes_4(0x60606060),
            "RX_TYPE": HBPF_SLT_VHEAD,
            "RX_RFS": bytes_3(rf_src),
            "RX_TGID": bytes_3(91),
            "RX_TIME": t0,
            "RX_START": t0,
        }
    )
    base = PacketSpec(dst_id=91, stream_id=0x50505050, rf_src=rf_src)

    ok = scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
        ingress_pkt_time=t0 + 0.1,
    )

    assert_inject_ok(ok)
    assert_forwarded(scenario, "MASTER-B", count=1, dst_id=91)
