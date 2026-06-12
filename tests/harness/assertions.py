# ADN DMR Peer Server - tests harness assertions
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

"""Reusable assertion helpers for deterministic harness tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adn_server.domain import int_id

if TYPE_CHECKING:
    from tests.harness.deterministic import CapturedPacket, DeterministicScenario


def packets_to(scenario: DeterministicScenario, system: str) -> list[CapturedPacket]:
    return scenario.capture.for_system(system)


def assert_forwarded(
    scenario: DeterministicScenario,
    system: str,
    *,
    count: int | None = 1,
    call_type: str | None = None,
    dst_id: int | None = None,
) -> list[CapturedPacket]:
    got = packets_to(scenario, system)
    if count is not None:
        assert len(got) == count, f"expected {count} packet(s) to {system!r}, got {len(got)}"
    for pkt in got:
        if call_type is not None:
            assert pkt.fields.get("call_type") == call_type, pkt.fields
        if dst_id is not None:
            assert int_id(pkt.fields["dst_id"]) == dst_id, pkt.fields
    return got


def assert_not_forwarded(scenario: DeterministicScenario, system: str) -> None:
    got = packets_to(scenario, system)
    assert got == [], f"expected no packets to {system!r}, got {len(got)}"


def assert_capture_unchanged(scenario: DeterministicScenario, system: str, before: int) -> None:
    after = len(packets_to(scenario, system))
    assert after == before, f"capture to {system!r} changed: {before} -> {after}"


def assert_report_event(scenario: DeterministicScenario, *substrings: str) -> None:
    assert scenario.report_factory is not None, "reporting not enabled on scenario"
    events = scenario.report_factory.events
    for sub in substrings:
        assert any(sub in ev for ev in events), f"no report event containing {sub!r}: {events}"


def assert_dmra_sent(
    scenario: DeterministicScenario,
    *,
    min_count: int = 1,
    payload_contains: bytes | None = None,
) -> None:
    assert len(scenario.dmra_capture) >= min_count
    if payload_contains is not None:
        payloads = [p for cap in scenario.dmra_capture for p in cap.packets]
        assert any(payload_contains in p for p in payloads), payloads


def assert_inject_ok(result: bool | None, *, expected: bool = True) -> None:
    if expected:
        assert result is not False, "inject returned False (dropped)"
    else:
        assert result is not True, f"inject should have dropped, got {result!r}"


def assert_all_dmr_fields(packets: list[CapturedPacket], **expected: Any) -> None:
    for pkt in packets:
        for key, value in expected.items():
            actual = pkt.fields.get(key)
            if key == "dst_id" and isinstance(value, int):
                actual = int_id(actual)
            assert actual == value, f"field {key}: expected {value!r}, got {actual!r}"
