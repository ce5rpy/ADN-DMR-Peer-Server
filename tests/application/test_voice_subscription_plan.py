"""Voice forward plan helpers (P2-009)."""

from __future__ import annotations

from adn_server.application.bridge_use_cases import BridgeUseCases
from adn_server.application.subscription.store_sync import replace_store_from_bridges
from adn_server.domain import bytes_3
from adn_server.domain.dmr.bptc import encode_emblc
from adn_server.infrastructure.bridge_router_impl import InMemoryBridgeRouter
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from adn_server.infrastructure.talker_alias_emblc import default_ta_emblc_encoder
from tests.application.test_subscription_router import _row
from tests.harness.deterministic import minimal_config


def _bridge(
    bridges: dict,
    *,
    use_subscription_router: bool,
) -> BridgeUseCases:
    config = minimal_config(("MASTER-A", "MASTER-B"))
    config["GLOBAL"]["USE_SUBSCRIPTION_ROUTER"] = use_subscription_router
    router = InMemoryBridgeRouter()
    router.set_bridges(bridges)
    store = InMemorySubscriptionStore()
    replace_store_from_bridges(store, bridges)
    return BridgeUseCases(
        router,
        config,
        encode_emblc=encode_emblc,
        ta_emblc_encoder=default_ta_emblc_encoder,
        subscription_store=store,
    )


def test_forward_plan_disabled_uses_legacy_tables():
    bridges = {
        "730444": [
            _row(system="MASTER-A", ts=1, tgid=730444, active=True),
            _row(system="MASTER-B", ts=1, tgid=730444, active=True),
        ]
    }
    bridge = _bridge(bridges, use_subscription_router=False)
    tables, leg_keys = bridge._voice_forward_plan(
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
    assert leg_keys is None


def test_forward_plan_enabled_returns_leg_filter():
    bridges = {
        "730444": [
            _row(system="MASTER-A", ts=1, tgid=730444, active=True),
            _row(system="MASTER-B", ts=1, tgid=730444, active=True),
            _row(system="OBP-CL", ts=1, tgid=730444, active=False),
        ]
    }
    bridge = _bridge(bridges, use_subscription_router=True)
    tables, leg_keys = bridge._voice_forward_plan(
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
    assert leg_keys == frozenset({("MASTER-B", 1, 730444)})
