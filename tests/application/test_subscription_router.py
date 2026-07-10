# ADN DMR Peer Server - tests application subscription router
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

"""SubscriptionRouter parity vs legacy BRIDGES scan (tests only)."""

from __future__ import annotations

from typing import Any

from adn_server.application.subscription.router import SubscriptionRouter
from adn_server.application.subscription.routing_table_import import subscriptions_from_routing_table
from adn_server.domain import bytes_3, int_id
from adn_server.domain.subscription import TgId
from adn_server.domain.voice_routing import ForwardLeg, VoiceIngress
from fakes.subscription_store import InMemorySubscriptionStore


def _legacy_relay_tables(
    bridges: dict[str, list[dict[str, Any]]],
    system_name: str,
    bridge_match_slot: int,
    dst_int: int,
) -> list[str]:
    dst_id_b = bytes_3(dst_int)
    result: list[str] = []
    for table_name, rows in bridges.items():
        for row in rows:
            if not row.get("ACTIVE"):
                continue
            if row.get("SYSTEM") != system_name:
                continue
            if int(row.get("TS") or 1) != bridge_match_slot:
                continue
            row_tgid = row.get("TGID") or b"\x00\x00\x00"
            if row_tgid == dst_id_b or int_id(row_tgid) == dst_int:
                result.append(table_name)
                break
    return result


def legacy_forward_targets(
    bridges: dict[str, list[dict[str, Any]]],
    *,
    source_system: str,
    slot: int,
    dst_tgid: int,
    source_is_obp: bool = False,
    openbridge_targets: frozenset[str] | None = None,
) -> set[tuple[str, int, int]]:
    """Minimal legacy forward set: (target_system, ts, tgid_int) from BRIDGES scan.

    When ``openbridge_targets`` is set, OBP dedup (``sys_ignore_obp``) applies only to those
    systems — matching ``routing_use_cases`` where dedup runs inside the OPENBRIDGE branch.
    """
    match_slot = 1 if source_is_obp else slot
    tables = _legacy_relay_tables(bridges, source_system, match_slot, dst_tgid)
    targets: set[tuple[str, int, int]] = set()
    seen_obp: set[tuple[str, int]] = set()
    for table in tables:
        for row in bridges.get(table, []):
            if row.get("SYSTEM") == source_system:
                continue
            if not row.get("ACTIVE"):
                continue
            ts = int(row.get("TS") or 1)
            target_system = str(row.get("SYSTEM"))
            if source_is_obp:
                apply_dedup = openbridge_targets is None or target_system in openbridge_targets
                if apply_dedup:
                    obp_key = (target_system, ts)
                    if obp_key in seen_obp:
                        continue
                    seen_obp.add(obp_key)
            targets.add((target_system, ts, int_id(row.get("TGID") or b"\x00\x00\x00")))
    return targets


def subscription_forward_targets(legs: tuple[ForwardLeg, ...]) -> set[tuple[str, int, int]]:
    return {(leg.target_system, int(leg.slot), int(leg.target_tgid)) for leg in legs}


def _row(
    *,
    system: str,
    ts: int,
    tgid: int,
    active: bool,
    to_type: str = "ON",
    timeout: float = 600.0,
) -> dict[str, Any]:
    tgid_b = bytes_3(tgid)
    return {
        "SYSTEM": system,
        "TS": ts,
        "TGID": tgid_b,
        "ACTIVE": active,
        "TIMEOUT": timeout,
        "TO_TYPE": to_type,
        "ON": [tgid_b],
        "OFF": [],
        "RESET": [],
        "TIMER": 0.0,
    }


def test_relay_tables_with_active_source_matches_legacy():
    bridges = {
        "730444": [
            _row(system="MASTER-A", ts=1, tgid=730444, active=True),
            _row(system="OBP-CL", ts=1, tgid=730444, active=True),
        ]
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table(bridges))
    sub_router = SubscriptionRouter(store)
    assert sub_router.relay_tables_with_active_source("MASTER-A", 1, 730444) == tuple(
        _legacy_relay_tables(bridges, "MASTER-A", 1, 730444)
    )


def test_resolve_matches_legacy_forward_targets():
    bridges = {
        "730444": [
            _row(system="MASTER-A", ts=1, tgid=730444, active=True),
            _row(system="OBP-CL", ts=1, tgid=730444, active=True),
            _row(system="MASTER-B", ts=1, tgid=730444, active=False),
        ]
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table(bridges))
    ingress = VoiceIngress(source_system="MASTER-A", slot=1, dst_tgid=TgId(730444))
    legs = SubscriptionRouter(store).resolve(ingress)
    assert subscription_forward_targets(legs) == legacy_forward_targets(
        bridges,
        source_system="MASTER-A",
        slot=1,
        dst_tgid=730444,
    )


def test_obp_ingress_forwards_to_all_active_hbp_slots():
    """OBP source on TS1; HBP targets on TS1+TS2 are separate legs (no sys_ignore_obp)."""
    bridges = {
        "730444": [
            _row(system="OBP-CL", ts=1, tgid=730444, active=True, to_type="STAT", timeout=""),
            _row(system="MASTER-A", ts=1, tgid=730444, active=True),
            _row(system="MASTER-A", ts=2, tgid=730444, active=True),
        ]
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table(bridges))
    router = SubscriptionRouter(store)
    assert router.relay_tables_with_active_source("OBP-CL", 1, 730444) == ("730444",)
    ingress = VoiceIngress(
        source_system="OBP-CL",
        slot=2,
        dst_tgid=TgId(730444),
        source_is_obp=True,
    )
    legs = SubscriptionRouter(store).resolve(ingress)
    assert subscription_forward_targets(legs) == legacy_forward_targets(
        bridges,
        source_system="OBP-CL",
        slot=2,
        dst_tgid=730444,
        source_is_obp=True,
        openbridge_targets=frozenset(),
    )
    assert len(legs) == 2
    assert {(leg.target_system, leg.slot) for leg in legs} == {("MASTER-A", 1), ("MASTER-A", 2)}


def test_resolve_obp_dedupes_same_openbridge_peer_across_tables():
    """Legacy sys_ignore_obp: same OPENBRIDGE (SYSTEM, TS) in two tables → one forward."""
    bridges = {
        "730444": [
            _row(system="OBP-CL", ts=1, tgid=730444, active=True, to_type="STAT", timeout=""),
            _row(system="OBP-PEER", ts=1, tgid=730444, active=True),
        ],
        "730445": [
            _row(system="OBP-CL", ts=1, tgid=730444, active=True),
            _row(system="OBP-PEER", ts=1, tgid=730444, active=True),
        ],
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table(bridges))
    ingress = VoiceIngress(
        source_system="OBP-CL",
        slot=2,
        dst_tgid=TgId(730444),
        source_is_obp=True,
    )
    legs = SubscriptionRouter(store).resolve(ingress)
    assert subscription_forward_targets(legs) == legacy_forward_targets(
        bridges,
        source_system="OBP-CL",
        slot=2,
        dst_tgid=730444,
        source_is_obp=True,
        openbridge_targets=frozenset({"OBP-PEER"}),
    )
    assert len(legs) == 1
    assert legs[0].target_system == "OBP-PEER"
    assert legs[0].slot == 1


def test_resolve_empty_when_no_active_source_row():
    bridges = {
        "730444": [
            _row(system="MASTER-A", ts=1, tgid=730444, active=False),
            _row(system="OBP-CL", ts=1, tgid=730444, active=True),
        ]
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table(bridges))
    ingress = VoiceIngress(source_system="MASTER-A", slot=1, dst_tgid=TgId(730444))
    assert SubscriptionRouter(store).resolve(ingress) == ()


def test_two_bridge_tables_same_dst_tgid():
    """Source active in one table only → forward targets only from that table."""
    bridges = {
        "730444": [
            _row(system="MASTER-A", ts=1, tgid=730444, active=True),
            _row(system="OBP-CL", ts=1, tgid=730444, active=True),
        ],
        "730445": [
            _row(system="MASTER-A", ts=1, tgid=730445, active=False),
            _row(system="MASTER-B", ts=1, tgid=730445, active=True),
        ],
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table(bridges))
    ingress = VoiceIngress(source_system="MASTER-A", slot=1, dst_tgid=TgId(730444))
    legs = SubscriptionRouter(store).resolve(ingress)
    assert subscription_forward_targets(legs) == {("OBP-CL", 1, 730444)}
