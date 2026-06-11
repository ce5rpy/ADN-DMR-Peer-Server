"""Voice forward plan helpers."""

from __future__ import annotations

from adn_server.application.routing_use_cases import RoutingUseCases
from adn_server.application.subscription.store_sync import replace_store_from_routing_table
from adn_server.domain import bytes_3
from adn_server.domain.subscription import TgId
from adn_server.domain.voice_routing import ForwardLeg
from adn_server.domain.dmr.bptc import encode_emblc
from adn_server.infrastructure.acl_router import InMemoryAclRouter
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from adn_server.infrastructure.talker_alias_emblc import default_ta_emblc_encoder
from tests.application.test_subscription_router import _row
from tests.harness.deterministic import minimal_config


def _routing(routing_table: dict) -> RoutingUseCases:
    config = minimal_config(("MASTER-A", "MASTER-B"))
    store = InMemorySubscriptionStore()
    replace_store_from_routing_table(store, routing_table)
    return RoutingUseCases(
        InMemoryAclRouter(),
        config,
        store,
        encode_emblc=encode_emblc,
        ta_emblc_encoder=default_ta_emblc_encoder,
    )


def test_forward_plan_returns_leg_filter() -> None:
    bridges = {
        "730444": [
            _row(system="MASTER-A", ts=1, tgid=730444, active=True),
            _row(system="MASTER-B", ts=1, tgid=730444, active=True),
            _row(system="OBP-CL", ts=1, tgid=730444, active=False),
        ]
    }
    routing = _routing(bridges)
    tables, legs = routing._voice_forward_plan(
        system_name="MASTER-A",
        peer_id=b"\x00\x00\x03\xe9",
        rf_src=b"\x00\x2f\x8b\x01",
        dst_id=bytes_3(730444),
        slot=1,
        call_type="group",
        stream_id=b"\x01\x02\x03\x04",
        source_is_obp=False,
        bridge_match_slot=1,
        dst_int=730444,
    )
    assert tables == ("730444",)
    assert legs == (ForwardLeg(target_system="MASTER-B", slot=1, target_tgid=TgId(730444)),)
