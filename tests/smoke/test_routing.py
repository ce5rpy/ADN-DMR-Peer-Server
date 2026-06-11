"""Smoke tests for basic HBP bridge forwarding."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_forwarded
from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_routing_table


@pytest.mark.smoke
def test_static_tg_routes_hbp_to_peer_master() -> None:
    """Regression: active bridge forwards HBP group voice to peer MASTER."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0x0A0B0C0D)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    for seq in range(1, 4):
        scenario.inject_hbp(
            "MASTER-A",
            DeterministicScenario.voice_burst_spec(base, seq=seq, dtype_vseq=seq),
        )

    assert_forwarded(scenario, "MASTER-B", count=4, call_type="group", dst_id=91)
