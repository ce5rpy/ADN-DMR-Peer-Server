"""Resolve forward legs from subscription store."""

from __future__ import annotations

from adn_server.application.subscription.router import SubscriptionRouter
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
from adn_server.domain.voice_routing import VoiceIngress
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def _sub(
    *,
    tgid: int,
    slot: int,
    system: str,
    active: bool,
    target: int | None = None,
) -> Subscription:
    phase = SubscriptionPhase.ACTIVE if active else SubscriptionPhase.IDLE
    return Subscription(
        channel=AudioChannel(tgid=TgId(tgid), slot=slot),  # type: ignore[arg-type]
        system=SystemId(system),
        target_tgid=TgId(target if target is not None else tgid),
        role=SubscriptionRole.SINK,
        policy=ActivationPolicy.INBAND,
        state=SubscriptionState(phase=phase),
    )


def test_resolve_returns_empty_when_source_inactive():
    store = InMemorySubscriptionStore()
    store.replace_all(
        [
            _sub(tgid=730444, slot=1, system="MASTER-A", active=False),
            _sub(tgid=730444, slot=1, system="OBP-CL", active=True),
        ]
    )
    router = SubscriptionRouter(store)
    ingress = VoiceIngress(source_system="MASTER-A", slot=1, dst_tgid=TgId(730444))
    assert router.resolve(ingress) == ()


def test_resolve_forwards_to_other_active_legs():
    store = InMemorySubscriptionStore()
    store.replace_all(
        [
            _sub(tgid=730444, slot=1, system="MASTER-A", active=True),
            _sub(tgid=730444, slot=1, system="OBP-CL", active=True),
            _sub(tgid=730444, slot=1, system="MASTER-B", active=False),
        ]
    )
    router = SubscriptionRouter(store)
    ingress = VoiceIngress(source_system="MASTER-A", slot=1, dst_tgid=TgId(730444))
    legs = router.resolve(ingress)
    assert len(legs) == 1
    assert legs[0].target_system == "OBP-CL"
    assert legs[0].slot == 1
    assert int(legs[0].target_tgid) == 730444


def test_obp_ingress_uses_ts1_for_source_match():
    store = InMemorySubscriptionStore()
    store.replace_all(
        [
            _sub(tgid=730444, slot=1, system="OBP-CL", active=True),
            _sub(tgid=730444, slot=1, system="MASTER-A", active=True),
        ]
    )
    router = SubscriptionRouter(store)
    ingress = VoiceIngress(
        source_system="OBP-CL",
        slot=2,
        dst_tgid=TgId(730444),
        source_is_obp=True,
    )
    legs = router.resolve(ingress)
    assert len(legs) == 1
    assert legs[0].target_system == "MASTER-A"
