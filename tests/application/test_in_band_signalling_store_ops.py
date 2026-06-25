# ADN DMR Peer Server - tests application in band signalling store ops
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>
#
###############################################################################
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software Foundation,
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
###############################################################################

"""Store-native in-band signalling."""

from __future__ import annotations

import copy

from tests.harness.deterministic import active_routing_table
from tests.harness.voice_helpers import reflector_routing_entry

from adn_server.application.subscription.in_band_signalling_ops import apply_in_band_signalling_store
from adn_server.application.subscription.store_sync import replace_store_from_routing_table
from adn_server.application.subscription.subscription_table_ops import make_static_tg_store
from adn_server.domain import bytes_3
from adn_server.domain.subscription import SubscriptionPhase
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def _store_from_bridges(bridges: dict) -> InMemorySubscriptionStore:
    store = InMemorySubscriptionStore()
    replace_store_from_routing_table(store, bridges)
    return store


def test_store_single_mode_deactivates_on_non_source_tg() -> None:
    store = _store_from_bridges(active_routing_table(52090, (("MASTER-A", 2),)))
    systems_cfg = {"MASTER-A": {"MODE": "MASTER", "SINGLE_MODE": True}}

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(91), 3000.0, systems_cfg)

    (sub,) = store.snapshot()
    assert sub.state.phase == SubscriptionPhase.IDLE


def test_store_non_single_keeps_bridge_on_arbitrary_vterm_tg() -> None:
    store = _store_from_bridges(active_routing_table(52090, (("MASTER-A", 2),)))
    systems_cfg = {"MASTER-A": {"MODE": "MASTER", "SINGLE_MODE": False}}

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(91), 3000.0, systems_cfg)

    (sub,) = store.snapshot()
    assert sub.state.phase == SubscriptionPhase.ACTIVE


def test_store_non_single_deactivates_on_tg4000() -> None:
    bridges = copy.deepcopy(active_routing_table(52090, (("MASTER-A", 2),)))
    store = _store_from_bridges(bridges)
    systems_cfg = {"MASTER-A": {"MODE": "MASTER", "SINGLE_MODE": False}}

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(4000), 3000.0, systems_cfg)

    (sub,) = store.snapshot()
    assert sub.state.phase == SubscriptionPhase.IDLE


def test_store_single_mode_keeps_static_off_on_unrelated_vterm() -> None:
    """OPTIONS static OFF legs must survive echo other-TG VTERM for OBP downlink."""
    store = InMemorySubscriptionStore()
    systems_cfg = {"MASTER-A": {"MODE": "MASTER", "SINGLE_MODE": True, "DEFAULT_UA_TIMER": 10}}
    make_static_tg_store(store, 52090, 2, 10.0, "MASTER-A", systems_cfg, 1000.0, single_mode=True)

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(9990), 3000.0, systems_cfg)

    sub = next(
        s for s in store.snapshot()
        if s.system.value == "MASTER-A" and int(s.target_tgid) == 52090
    )
    assert sub.is_active()


def test_store_reflector_ignored_when_vterm_not_on_tg9() -> None:
    bridges = active_routing_table(52090, (("MASTER-A", 2),))
    bridges.update(reflector_routing_entry())
    store = _store_from_bridges(bridges)
    reflector = next(s for s in store.snapshot() if s.relay_table_key == "#310")
    timer_before = reflector.state.timer_expires_at

    apply_in_band_signalling_store(store, "MASTER-A", 2, bytes_3(52090), 2000.0, {})

    reflector = store.get(reflector.subscription_id)
    assert reflector is not None
    assert reflector.state.timer_expires_at == timer_before
    assert reflector.is_active()
