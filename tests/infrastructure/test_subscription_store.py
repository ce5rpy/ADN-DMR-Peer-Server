# ADN DMR Peer Server - tests infrastructure subscription store
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

"""In-memory subscription store."""

from __future__ import annotations

from adn_server.domain.subscription import (
    ActivationPolicy,
    AudioChannel,
    Subscription,
    SubscriptionId,
    SubscriptionPhase,
    SubscriptionRole,
    SubscriptionState,
    SystemId,
    TgId,
)
from adn_server.infrastructure.subscription_store import InMemorySubscriptionStore


def _leg(
    *,
    tgid: int,
    slot: int,
    system: str,
    target: int | None = None,
    phase: SubscriptionPhase = SubscriptionPhase.IDLE,
) -> Subscription:
    return Subscription(
        channel=AudioChannel(tgid=TgId(tgid), slot=slot),  # type: ignore[arg-type]
        system=SystemId(system),
        target_tgid=TgId(target if target is not None else tgid),
        role=SubscriptionRole.SINK,
        policy=ActivationPolicy.STATIC,
        state=SubscriptionState(phase=phase),
    )


def test_upsert_get_remove():
    store = InMemorySubscriptionStore()
    sub = _leg(tgid=730444, slot=2, system="MASTER-A")
    store.upsert(sub)
    sub_id = SubscriptionId(channel=sub.channel, system=sub.system)
    assert store.get(sub_id) is sub
    assert store.remove(sub_id) is True
    assert store.get(sub_id) is None
    assert store.remove(sub_id) is False


def test_replace_all_and_snapshot():
    store = InMemorySubscriptionStore()
    a = _leg(tgid=1, slot=1, system="A")
    b = _leg(tgid=2, slot=2, system="B")
    store.replace_all([a, b])
    snap = store.snapshot()
    assert len(snap) == 2
    assert a in snap and b in snap
    store.replace_all([a])
    assert store.snapshot() == (a,)


def test_list_by_channel_system_and_active():
    store = InMemorySubscriptionStore()
    channel = AudioChannel(tgid=TgId(730444), slot=2)
    idle = _leg(tgid=730444, slot=2, system="OBP-CL", phase=SubscriptionPhase.IDLE)
    active = _leg(tgid=730444, slot=2, system="ECHO", phase=SubscriptionPhase.ACTIVE)
    other = _leg(tgid=9990, slot=1, system="ECHO")
    store.replace_all([idle, active, other])

    by_channel = store.list_by_channel(channel)
    assert len(by_channel) == 2
    assert idle in by_channel and active in by_channel

    by_system = store.list_by_system(SystemId("ECHO"))
    assert len(by_system) == 2
    assert active in by_system and other in by_system

    assert store.list_active() == (active,)
    assert store.list_by_phase(SubscriptionPhase.IDLE) == (idle, other)


def test_clear():
    store = InMemorySubscriptionStore()
    store.upsert(_leg(tgid=1, slot=1, system="X"))
    store.clear()
    assert store.snapshot() == ()
