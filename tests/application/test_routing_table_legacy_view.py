"""RoutingTableLegacyView: subscription store → pickle BRIDGE_SND shim."""

from __future__ import annotations

import pickle

from adn_server.application.subscription.routing_table_export import export_routing_table
from adn_server.application.subscription.routing_table_legacy_view import RoutingTableLegacyView
from adn_server.infrastructure.twisted_adapters.report.pickle_legacy import encode_bridge_snd_frame
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
from adn_server.infrastructure.twisted_adapters.report.opcodes import REPORT_OPCODES


def _sample_store() -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    store.upsert(
        Subscription(
            channel=AudioChannel(tgid=TgId(730444), slot=1),
            system=SystemId("MASTER-A"),
            target_tgid=TgId(730444),
            role=SubscriptionRole.SINK,
            policy=ActivationPolicy.INBAND,
            state=SubscriptionState(phase=SubscriptionPhase.ACTIVE),
        )
    )
    return store


def test_generate_matches_export_routing_table():
    store = _sample_store()
    view = RoutingTableLegacyView(store)
    now = 1_700_000_000.0
    assert view.generate(now=now) == export_routing_table(store, now=now)


def test_bridge_snd_frame_is_pickle_protocol_2():
    store = _sample_store()
    frame = encode_bridge_snd_frame(RoutingTableLegacyView(store).generate())
    assert frame[:1] == REPORT_OPCODES["BRIDGE_SND"]
    bridges = pickle.loads(frame[1:], encoding="bytes")
    assert "730444" in bridges
    row = bridges["730444"][0]
    assert row["SYSTEM"] == "MASTER-A"
    assert row["TGID"] == bytes_3(730444)
    assert isinstance(row["ACTIVE"], bool)
