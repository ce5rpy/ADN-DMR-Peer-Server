# ADN DMR Peer Server - tests application voice ingress builder
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

"""Build VoiceIngress from DMRD parameters."""

from __future__ import annotations

from adn_server.application.subscription.ingress import build_voice_ingress
from adn_server.application.subscription.router import SubscriptionRouter
from adn_server.domain import bytes_3, bytes_4
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


def test_build_voice_ingress_hbp_group():
    ingress = build_voice_ingress(
        source_system="MASTER-A",
        system_mode="MASTER",
        peer_id=bytes_4(1234),
        rf_src=bytes_3(73010),
        dst_id=bytes_3(730444),
        slot=2,
        call_type="group",
        stream_id=bytes_4(99),
    )
    assert ingress is not None
    assert ingress.source_system == "MASTER-A"
    assert ingress.slot == 2
    assert ingress.source_is_obp is False
    assert ingress.bridge_match_slot == 2
    assert int(ingress.dst_tgid) == 730444
    assert ingress.call_type == "group"
    assert ingress.stream_id == 99
    assert ingress.peer_id is not None and int(ingress.peer_id) == 1234
    assert ingress.src_id is not None and int(ingress.src_id) == 73010


def test_build_voice_ingress_obp_preserves_packet_slot_for_metadata():
    ingress = build_voice_ingress(
        source_system="OBP-CL",
        system_mode="OPENBRIDGE",
        peer_id=bytes_4(1),
        rf_src=bytes_3(73010),
        dst_id=bytes_3(730444),
        slot=2,
        call_type="group",
    )
    assert ingress is not None
    assert ingress.slot == 2
    assert ingress.source_is_obp is True
    assert ingress.bridge_match_slot == 1


def test_build_voice_ingress_none_for_unit_call():
    assert (
        build_voice_ingress(
            source_system="MASTER-A",
            system_mode="MASTER",
            peer_id=bytes_4(1),
            rf_src=bytes_3(73010),
            dst_id=bytes_3(730444),
            slot=1,
            call_type="unit",
        )
        is None
    )


def test_built_ingress_resolves_same_as_manual_obp_ingress():
    store = InMemorySubscriptionStore()
    store.replace_all(
        [
            Subscription(
                channel=AudioChannel(tgid=TgId(730444), slot=1),
                system=SystemId("OBP-CL"),
                target_tgid=TgId(730444),
                role=SubscriptionRole.PASSIVE_STAT,
                policy=ActivationPolicy.INBAND,
                state=SubscriptionState(phase=SubscriptionPhase.ACTIVE),
            ),
            Subscription(
                channel=AudioChannel(tgid=TgId(730444), slot=1),
                system=SystemId("MASTER-A"),
                target_tgid=TgId(730444),
                role=SubscriptionRole.SINK,
                policy=ActivationPolicy.INBAND,
                state=SubscriptionState(phase=SubscriptionPhase.ACTIVE),
            ),
        ]
    )
    ingress = build_voice_ingress(
        source_system="OBP-CL",
        system_mode="OPENBRIDGE",
        peer_id=bytes_4(1),
        rf_src=bytes_3(73010),
        dst_id=bytes_3(730444),
        slot=2,
        call_type="group",
    )
    assert ingress is not None
    legs = SubscriptionRouter(store).resolve(ingress)
    assert len(legs) == 1
    assert legs[0].target_system == "MASTER-A"
