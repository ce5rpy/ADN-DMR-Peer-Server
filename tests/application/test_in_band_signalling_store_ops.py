"""Store-native in-band signalling."""

from __future__ import annotations

import copy

from adn_server.application.subscription.in_band_signalling_ops import apply_in_band_signalling_store
from adn_server.application.subscription.store_sync import replace_store_from_bridges
from adn_server.domain import bytes_3
from adn_server.domain.subscription import SubscriptionPhase
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore
from tests.harness.deterministic import active_bridge
from tests.harness.voice_helpers import reflector_bridge_entry


def _store_from_bridges(bridges: dict) -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    replace_store_from_bridges(store, bridges)
    return store


def test_store_single_mode_deactivates_on_non_source_tg() -> None:
    store = _store_from_bridges(active_bridge(52090, (("MASTER-A", 2),)))
    systems_cfg = {"MASTER-A": {"MODE": "MASTER", "SINGLE_MODE": True}}

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(91), 3000.0, systems_cfg)

    (sub,) = store.snapshot()
    assert sub.state.phase == SubscriptionPhase.IDLE


def test_store_non_single_keeps_bridge_on_arbitrary_vterm_tg() -> None:
    store = _store_from_bridges(active_bridge(52090, (("MASTER-A", 2),)))
    systems_cfg = {"MASTER-A": {"MODE": "MASTER", "SINGLE_MODE": False}}

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(91), 3000.0, systems_cfg)

    (sub,) = store.snapshot()
    assert sub.state.phase == SubscriptionPhase.ACTIVE


def test_store_non_single_deactivates_on_tg4000() -> None:
    bridges = copy.deepcopy(active_bridge(52090, (("MASTER-A", 2),)))
    store = _store_from_bridges(bridges)
    systems_cfg = {"MASTER-A": {"MODE": "MASTER", "SINGLE_MODE": False}}

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(4000), 3000.0, systems_cfg)

    (sub,) = store.snapshot()
    assert sub.state.phase == SubscriptionPhase.IDLE


def test_store_reflector_ignored_when_vterm_not_on_tg9() -> None:
    bridges = active_bridge(52090, (("MASTER-A", 2),))
    bridges.update(reflector_bridge_entry())
    store = _store_from_bridges(bridges)
    reflector = next(s for s in store.snapshot() if s.bridge_key == "#310")
    timer_before = reflector.state.timer_expires_at

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(52090), 2000.0, {})

    reflector = store.get(reflector.subscription_id)
    assert reflector is not None
    assert reflector.state.timer_expires_at == timer_before
    assert reflector.is_active()
