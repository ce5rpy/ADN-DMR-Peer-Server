# ADN DMR Peer Server - tests routing crc dedup
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

"""CRC payload dedup: only seq > 0 triggers drop."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_forwarded, assert_inject_ok
from tests.harness.deterministic import (
    DeterministicScenario,
    PacketSpec,
    active_routing_table,
    add_openbridge_system,
    patch_routing_wall_time,
)


def test_hbp_crc_dedup_drops_duplicate_seq_gt_zero() -> None:
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0xABCD1234)
    burst = DeterministicScenario.voice_burst_spec(base, seq=2, dtype_vseq=2)
    t0 = scenario.clock.time()

    scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_head_spec(base),
        ingress_pkt_time=t0,
    )
    scenario.inject_hbp("MASTER-A", burst, ingress_pkt_time=t0 + 0.06)
    ok = scenario.inject_hbp("MASTER-A", burst, ingress_pkt_time=t0 + 0.12)
    assert not ok


@pytest.mark.behavior
def test_hbp_crc_dedup_allows_seq_zero_repeat() -> None:
    """Regression: duplicate VHEAD with seq 0 still forwards (not subject to crc dedup)."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    base = PacketSpec(dst_id=91, stream_id=0xDEADBEEF, seq=0)
    vhead = DeterministicScenario.voice_head_spec(base)
    t0 = scenario.clock.time()

    ok1 = scenario.inject_hbp("MASTER-A", vhead, ingress_pkt_time=t0)
    ok2 = scenario.inject_hbp("MASTER-A", vhead, ingress_pkt_time=t0 + 0.06)
    assert_inject_ok(ok1)
    assert_inject_ok(ok2)
    assert_forwarded(scenario, "MASTER-B", count=2, dst_id=91)


def test_obp_crc_dedup_drops_duplicate_seq_gt_zero() -> None:
    bridges = active_routing_table(52090, (("OBP-CL", 1), ("MASTER-A", 2)))
    config = DeterministicScenario().config
    add_openbridge_system(config, "OBP-CL")
    config["SYSTEMS"]["MASTER-A"]["TS2_STATIC"] = "52090"
    scenario = DeterministicScenario(config=config, routing_table=bridges)
    base = PacketSpec(dst_id=52090, stream_id=0xCAFEBABE, slot=1)
    burst = DeterministicScenario.voice_burst_spec(base, seq=3, dtype_vseq=3)

    with patch_routing_wall_time(scenario.clock):
        scenario.inject_obp("OBP-CL", DeterministicScenario.voice_head_spec(base))
        scenario.inject_obp("OBP-CL", burst)
        ok = scenario.inject_obp("OBP-CL", burst)
        assert not ok
