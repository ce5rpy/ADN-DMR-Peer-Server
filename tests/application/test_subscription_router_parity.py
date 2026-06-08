"""Parity helpers: legacy BRIDGES vs SubscriptionRouter (tests only)."""

from __future__ import annotations

from typing import Any

from adn_server.application.subscription.router import SubscriptionRouter
from adn_server.domain import bytes_3, int_id
from adn_server.domain.subscription import (
    ActivationPolicy,
    AudioChannel,
    Subscription,
    SubscriptionPhase,
    SubscriptionRole,
    SubscriptionState,
    SystemId,
    TgId,
)
from adn_server.domain.voice_routing import ForwardLeg, VoiceIngress
from adn_server.infrastructure.bridge_router_impl import InMemoryBridgeRouter
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def _role_from_to_type(to_type: str) -> SubscriptionRole:
    if to_type == "NONE":
        return SubscriptionRole.ECHO
    if to_type == "STAT":
        return SubscriptionRole.PASSIVE_STAT
    return SubscriptionRole.SINK


def subscriptions_from_bridges(bridges: dict[str, list[dict[str, Any]]]) -> list[Subscription]:
    """Build subscriptions that round-trip ``export_bridges`` shape for parity tests."""
    subs: list[Subscription] = []
    for table_key, rows in bridges.items():
        for row in rows:
            if not isinstance(row, dict):
                continue
            ts = int(row.get("TS") or 1)
            if table_key.startswith("#"):
                channel_tgid = int_id(row.get("TGID") or b"\x00\x00\x00")
            else:
                channel_tgid = int(table_key)
            to_type = str(row.get("TO_TYPE", "ON"))
            subs.append(
                Subscription(
                    channel=AudioChannel(tgid=TgId(channel_tgid), slot=ts),  # type: ignore[arg-type]
                    system=SystemId(str(row.get("SYSTEM", ""))),
                    target_tgid=TgId(int_id(row.get("TGID") or b"\x00\x00\x00")),
                    role=_role_from_to_type(to_type),
                    policy=ActivationPolicy.INBAND,
                    state=SubscriptionState(
                        phase=SubscriptionPhase.ACTIVE if row.get("ACTIVE") else SubscriptionPhase.IDLE
                    ),
                    bridge_key=table_key if table_key.startswith("#") else None,
                    timeout_seconds=row.get("TIMEOUT") if isinstance(row.get("TIMEOUT"), (int, float)) else None,
                )
            )
    return subs


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
    systems — matching ``bridge_use_cases`` where dedup runs inside the OPENBRIDGE branch.
    """
    router = InMemoryBridgeRouter()
    router.set_bridges(bridges)
    match_slot = 1 if source_is_obp else slot
    tables = router.bridge_tables_with_active_source(source_system, match_slot, dst_tgid)
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


def test_bridge_tables_with_active_source_matches_legacy():
    bridges = {
        "730444": [
            _row(system="MASTER-A", ts=1, tgid=730444, active=True),
            _row(system="OBP-CL", ts=1, tgid=730444, active=True),
        ]
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_bridges(bridges))
    sub_router = SubscriptionRouter(store)
    legacy = InMemoryBridgeRouter()
    legacy.set_bridges(bridges)
    assert sub_router.bridge_tables_with_active_source("MASTER-A", 1, 730444) == tuple(
        legacy.bridge_tables_with_active_source("MASTER-A", 1, 730444)
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
    store.replace_all(subscriptions_from_bridges(bridges))
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
    store.replace_all(subscriptions_from_bridges(bridges))
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
    store.replace_all(subscriptions_from_bridges(bridges))
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
    store.replace_all(subscriptions_from_bridges(bridges))
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
    store.replace_all(subscriptions_from_bridges(bridges))
    ingress = VoiceIngress(source_system="MASTER-A", slot=1, dst_tgid=TgId(730444))
    legs = SubscriptionRouter(store).resolve(ingress)
    assert subscription_forward_targets(legs) == {("OBP-CL", 1, 730444)}
