"""Domain subscription entities."""

from __future__ import annotations

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


def _sub(*, phase: SubscriptionPhase = SubscriptionPhase.IDLE, active: bool = False) -> Subscription:
    state = SubscriptionState(
        phase=SubscriptionPhase.ACTIVE if active else phase,
        timer_expires_at=100.0 if active else None,
    )
    return Subscription(
        channel=AudioChannel(tgid=TgId(730444), slot=2),
        system=SystemId("OBP-CL"),
        target_tgid=TgId(730444),
        role=SubscriptionRole.SINK,
        policy=ActivationPolicy.INBAND,
        state=state,
    )


def test_subscription_id_stable():
    sub = _sub()
    assert sub.subscription_id.channel == sub.channel
    assert sub.subscription_id.system == sub.system


def test_is_active():
    assert not _sub().is_active()
    assert _sub(active=True).is_active()
