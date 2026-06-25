"""Smoke tests for PacketSpec and DMR header parsing."""

from __future__ import annotations

from tests.harness.deterministic import PacketSpec, parse_dmr_fields

from adn_server.domain import int_id


def test_packet_spec_builds_valid_dmr_header() -> None:
    spec = PacketSpec(dst_id=91, rf_src=3120001, peer_id=1001, seq=7)
    packet = spec.data()
    fields = parse_dmr_fields(packet)

    assert fields["opcode"] == b"DMRD"
    assert fields["seq"] == 7
    assert int_id(fields["dst_id"]) == 91
    assert int_id(fields["rf_src"]) == 3120001
    assert fields["slot"] == 2
    assert fields["call_type"] == "group"
