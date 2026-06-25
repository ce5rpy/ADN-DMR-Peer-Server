# ADN DMR Peer Server - tests infrastructure peer downlink fanout
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

"""Inject-only MASTER: downlink index limits send_peer fan-out."""

from __future__ import annotations

import pytest
from tests.harness.deterministic import DeterministicScenario, PacketSpec
from tests.support.hbp_repeat_stack import build_hbp_repeat_stack

from adn_server.domain import bytes_4
from adn_server.infrastructure.hbp_constants import DMRD

pytestmark = pytest.mark.integration

_TG = 52090


def _voice_burst(peer_id: bytes, rf_src: int = 7300444) -> bytes:
    spec = PacketSpec(
        peer_id=int.from_bytes(peer_id, "big"),
        rf_src=rf_src,
        dst_id=_TG,
        slot=2,
        stream_id=0x11223344,
        payload=b"\x00" * 33,
    )
    return DeterministicScenario.voice_burst_spec(spec, seq=1, dtype_vseq=1).data()


def test_send_peers_scales_with_matching_options_not_total_peers() -> None:
    stack = build_hbp_repeat_stack(talker_alias=False, system_name="MASTER-A")
    stack.config["PROXY"] = {"TARGET_SYSTEM": "MASTER-A"}
    stack.hbp._CONFIG = stack.config

    tx = bytes_4(730044401)
    match = bytes_4(730044402)
    stack.register_peer(tx, ("10.0.0.10", 62010), options=f"TS2={_TG};")
    stack.register_peer(match, ("10.0.0.11", 62011), options=f"TS2={_TG};")

    extras = []
    for i in range(50):
        pid = bytes_4(730100000 + i)
        extras.append(pid)
        stack.register_peer(pid, (f"10.1.0.{i}", 62100 + i), options="TS2=91;")

    stack.hbp._refresh_connected_peer_count()
    stack.hbp._mark_downlink_index_dirty()

    burst = _voice_burst(tx)
    stack.transport.clear()
    stack.hbp.send_peers(burst)

    dmrd_sends = [pkt for pkt, _ in stack.transport.sent if pkt[:4] == DMRD]
    # TX peer + one matching peer (not 50 unrelated hotspots).
    assert len(dmrd_sends) == 2
