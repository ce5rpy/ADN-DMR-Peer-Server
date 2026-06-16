# ADN DMR Peer Server - tests hbp hbp loop control
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

"""HBP vs HBP loop control (ingress packet control)."""

from __future__ import annotations

import pytest
from tests.harness.assertions import assert_capture_unchanged, assert_inject_ok
from tests.harness.deterministic import DeterministicScenario, PacketSpec, active_routing_table


def test_hbp_loop_loser_when_other_hbp_owns_stream() -> None:
    """Second HBP source loses when another MASTER slot already has RX_STREAM_ID."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    stream_id = 0x41414141
    scenario.seed_hbp_slot_stream("MASTER-B", 2, stream_id, tgid=91)
    base = PacketSpec(dst_id=91, stream_id=stream_id, slot=2)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    ok = scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )

    assert_inject_ok(ok, expected=False)
    assert scenario.protocols["MASTER-A"].STATUS[2].get("LOOPLOG") is True


@pytest.mark.behavior
def test_hbp_loop_winner_forwards_until_loser_detected() -> None:
    """Regression: VHEAD bridges; loop loser burst does not add forwards."""
    bridges = active_routing_table(91, (("MASTER-A", 2), ("MASTER-B", 2)))
    scenario = DeterministicScenario(routing_table=bridges)
    stream_id = 0x42424242
    scenario.seed_hbp_slot_stream("MASTER-B", 2, stream_id, tgid=91)
    base = PacketSpec(dst_id=91, stream_id=stream_id, slot=2)

    scenario.inject_hbp("MASTER-A", DeterministicScenario.voice_head_spec(base))
    forwarded_after_vhead = len(scenario.capture.for_system("MASTER-B"))

    ok = scenario.inject_hbp(
        "MASTER-A",
        DeterministicScenario.voice_burst_spec(base, seq=1, dtype_vseq=1),
    )
    assert_capture_unchanged(scenario, "MASTER-B", forwarded_after_vhead)
    assert_inject_ok(ok, expected=False)
