"""Hot-path indexes on InMemorySubscriptionStore."""

from __future__ import annotations

from adn_server.application.subscription.router import SubscriptionRouter
from adn_server.application.subscription.routing_table_import import subscriptions_from_routing_table
from adn_server.domain import bytes_3
from adn_server.domain.subscription import SubscriptionPhase
from adn_server.domain.voice_routing import VoiceIngress
from adn_server.domain.value_objects import TgId
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def _row(*, system: str, ts: int, tgid: int, active: bool) -> dict:
    return {
        "SYSTEM": system,
        "TS": ts,
        "TGID": bytes_3(tgid),
        "ACTIVE": active,
        "TIMEOUT": 600.0,
        "TO_TYPE": "OFF" if active else "ON",
        "ON": [bytes_3(tgid)],
        "OFF": [],
        "RESET": [],
        "TIMER": 0.0,
    }


def test_relay_tables_index_matches_full_scan() -> None:
    bridges = {
        "7147": [
            _row(system="OBP-CL", ts=1, tgid=7147, active=True),
            _row(system="SYSTEM", ts=2, tgid=7147, active=True),
        ]
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table(bridges))
    router = SubscriptionRouter(store)
    assert store.relay_tables_with_active_source("OBP-CL", 1, 7147) == ("7147",)
    assert router.relay_tables_with_active_source("OBP-CL", 1, 7147) == ("7147",)


def test_has_active_target_leg_tracks_upsert() -> None:
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table({"7147": [_row(system="SYSTEM", ts=2, tgid=7147, active=True)]}))
    assert store.has_active_target_leg("SYSTEM", 2, 7147) is True
    sub = store.snapshot()[0]
    from dataclasses import replace

    idle = replace(sub, state=replace(sub.state, phase=SubscriptionPhase.IDLE))
    store.upsert(idle)
    assert store.has_active_target_leg("SYSTEM", 2, 7147) is False


def test_resolve_uses_table_index() -> None:
    bridges = {
        "7147": [
            _row(system="OBP-CL", ts=1, tgid=7147, active=True),
            _row(system="SYSTEM", ts=2, tgid=7147, active=True),
        ]
    }
    store = InMemorySubscriptionStore()
    store.replace_all(subscriptions_from_routing_table(bridges))
    legs = SubscriptionRouter(store).resolve(
        VoiceIngress(source_system="OBP-CL", slot=1, dst_tgid=TgId(7147), source_is_obp=True)
    )
    assert len(legs) == 1
    assert legs[0].target_system == "SYSTEM"
