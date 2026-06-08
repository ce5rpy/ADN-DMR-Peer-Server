"""One-way BRIDGES export from subscriptions."""

from __future__ import annotations

from adn_server.application.subscription.bridges_export import export_bridges, subscription_to_legacy_row
from adn_server.domain import bytes_3
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
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def test_subscription_to_legacy_row_echo():
    now = 1_700_000_000.0
    sub = Subscription(
        channel=AudioChannel(tgid=TgId(9990), slot=2),
        system=SystemId("ECHO"),
        target_tgid=TgId(9990),
        role=SubscriptionRole.ECHO,
        policy=ActivationPolicy.INBAND,
        state=SubscriptionState(phase=SubscriptionPhase.ACTIVE, timer_expires_at=now + 120),
        timeout_seconds=120.0,
    )
    row = subscription_to_legacy_row(sub, now=now)
    assert row["SYSTEM"] == "ECHO"
    assert row["TS"] == 2
    assert row["TGID"] == bytes_3(9990)
    assert row["ACTIVE"] is True
    assert row["TO_TYPE"] == "NONE"
    assert row["TIMEOUT"] == 120.0
    assert row["TIMER"] == now + 120


def test_subscription_to_legacy_row_stat_obp():
    sub = Subscription(
        channel=AudioChannel(tgid=TgId(730444), slot=1),
        system=SystemId("OBP-CL"),
        target_tgid=TgId(730444),
        role=SubscriptionRole.PASSIVE_STAT,
        policy=ActivationPolicy.OPENBRIDGE_STAT,
        state=SubscriptionState(phase=SubscriptionPhase.ACTIVE),
    )
    row = subscription_to_legacy_row(sub)
    assert row["TO_TYPE"] == "STAT"
    assert row["TIMEOUT"] == ""
    assert row["ON"] == []


def test_export_bridges_groups_by_table_key():
    store = InMemorySubscriptionStore()
    channel = AudioChannel(tgid=TgId(730444), slot=1)
    store.upsert(
        Subscription(
            channel=channel,
            system=SystemId("MASTER-A"),
            target_tgid=TgId(730444),
            role=SubscriptionRole.SINK,
            policy=ActivationPolicy.INBAND,
            state=SubscriptionState(phase=SubscriptionPhase.IDLE),
        )
    )
    store.upsert(
        Subscription(
            channel=AudioChannel(tgid=TgId(730444), slot=2),
            system=SystemId("MASTER-A"),
            target_tgid=TgId(730444),
            role=SubscriptionRole.SINK,
            policy=ActivationPolicy.INBAND,
            state=SubscriptionState(phase=SubscriptionPhase.IDLE),
        )
    )
    store.upsert(
        Subscription(
            channel=AudioChannel(tgid=TgId(9990), slot=1),
            system=SystemId("OBP-CL"),
            target_tgid=TgId(9990),
            role=SubscriptionRole.PASSIVE_STAT,
            policy=ActivationPolicy.OPENBRIDGE_STAT,
            state=SubscriptionState(phase=SubscriptionPhase.ACTIVE),
            bridge_key="730444",
        )
    )
    bridges = export_bridges(store)
    assert set(bridges.keys()) == {"730444"}
    assert len(bridges["730444"]) == 3


def test_static_active_uses_off_to_type():
    sub = Subscription(
        channel=AudioChannel(tgid=TgId(12345), slot=1),
        system=SystemId("MASTER-A"),
        target_tgid=TgId(12345),
        role=SubscriptionRole.SINK,
        policy=ActivationPolicy.STATIC,
        state=SubscriptionState(phase=SubscriptionPhase.ACTIVE),
    )
    row = subscription_to_legacy_row(sub)
    assert row["TO_TYPE"] == "OFF"
    assert row["ACTIVE"] is True
    assert row["ON"] == [bytes_3(12345)]
