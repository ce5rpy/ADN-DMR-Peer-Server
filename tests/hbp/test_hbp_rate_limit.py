# ADN DMR Peer Server - tests hbp hbp rate limit
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
