"""BRIDGES → Subscription import (policy / role parity)."""

from __future__ import annotations

from adn_server.application.subscription.routing_table_import import subscriptions_from_routing_table
from adn_server.domain import bytes_3
from adn_server.domain.subscription import (
    ActivationPolicy,
    SubscriptionPhase,
    SubscriptionRole,
)


def test_import_echo_and_inband_rows():
    tgid_b = bytes_3(9990)
    bridges = {
        "9990": [
            {
                "SYSTEM": "ECHO",
                "TS": 2,
                "TGID": tgid_b,
                "ACTIVE": True,
                "TIMEOUT": 120.0,
                "TO_TYPE": "NONE",
            },
            {
                "SYSTEM": "MASTER-A",
                "TS": 1,
                "TGID": tgid_b,
                "ACTIVE": False,
                "TIMEOUT": 600.0,
                "TO_TYPE": "ON",
            },
        ]
    }
    subs = subscriptions_from_routing_table(bridges)
    assert len(subs) == 2
    echo, master = subs
    assert echo.role == SubscriptionRole.ECHO
    assert echo.policy == ActivationPolicy.INBAND
    assert echo.state.phase == SubscriptionPhase.ACTIVE
    assert master.role == SubscriptionRole.SINK
    assert master.policy == ActivationPolicy.INBAND
    assert master.state.phase == SubscriptionPhase.IDLE


def test_import_static_and_stat_rows():
    bridges = {
        "12345": [
            {
                "SYSTEM": "MASTER-A",
                "TS": 1,
                "TGID": bytes_3(12345),
                "ACTIVE": True,
                "TIMEOUT": 600.0,
                "TO_TYPE": "OFF",
            },
            {
                "SYSTEM": "OBP-CL",
                "TS": 1,
                "TGID": bytes_3(12345),
                "ACTIVE": True,
                "TIMEOUT": "",
                "TO_TYPE": "STAT",
            },
        ]
    }
    subs = subscriptions_from_routing_table(bridges)
    static, stat = subs
    assert static.policy == ActivationPolicy.STATIC
    assert static.role == SubscriptionRole.SINK
    assert stat.policy == ActivationPolicy.OPENBRIDGE_STAT
    assert stat.role == SubscriptionRole.PASSIVE_STAT


def test_import_hash_table_key_sets_relay_table_key():
    bridges = {
        "#730444": [
            {
                "SYSTEM": "OBP-CL",
                "TS": 1,
                "TGID": bytes_3(730444),
                "ACTIVE": True,
                "TIMEOUT": "",
                "TO_TYPE": "STAT",
            }
        ]
    }
    (sub,) = subscriptions_from_routing_table(bridges)
    assert sub.relay_table_key == "#730444"


def test_import_preserves_on_off_reset_triggers():
    tg = bytes_3(52090)
    off_tg = bytes_3(91)
    bridges = {
        "52090": [
            {
                "SYSTEM": "MASTER-A",
                "TS": 2,
                "TGID": tg,
                "ACTIVE": True,
                "TIMEOUT": 60.0,
                "TO_TYPE": "ON",
                "ON": [tg],
                "OFF": [off_tg],
                "RESET": [bytes_3(4000)],
            }
        ]
    }
    (sub,) = subscriptions_from_routing_table(bridges)
    assert sub.triggers.on == (tg,)
    assert sub.triggers.off == (off_tg,)
    assert sub.triggers.reset == (bytes_3(4000),)
