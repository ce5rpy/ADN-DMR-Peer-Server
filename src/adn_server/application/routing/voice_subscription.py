# ADN DMR Peer Server - application routing voice subscription
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
#
# Derived from ADN DMR Server / FreeDMR / HBlink. Original license:
###############################################################################
# Copyright (C) 2026 Joaquin Madrid Belando, EA5GVK <ea5gvk@gmail.com>
# Copyright (C) 2020 Simon Adlem, G7RZU <g7rzu@gb7fr.org.uk>
# Copyright (C) 2016-2019 Cortney T. Buffington, N0MJS <n0mjs@me.com>
#
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

"""Subscription router helpers for the voice hot path."""

from __future__ import annotations

import logging

from ..ports import SubscriptionStore
from ..subscription.ingress import build_voice_ingress
from ..subscription.router import SubscriptionRouter
from ...domain.voice_routing import ForwardLeg, VoiceIngress

logger = logging.getLogger(__name__)


class VoiceSubscriptionMixin:
    """Wire ``SubscriptionRouter`` into ``dmrd_received``."""

    _subscription_store: SubscriptionStore
    _subscription_router: SubscriptionRouter | None

    def _subscription_router_instance(self) -> SubscriptionRouter:
        router = getattr(self, "_subscription_router", None)
        if router is None:
            router = SubscriptionRouter(self._subscription_store)
            self._subscription_router = router
        return router

    def _build_dmrd_voice_ingress(
        self,
        *,
        system_name: str,
        peer_id: bytes,
        rf_src: bytes,
        dst_id: bytes,
        slot: int,
        call_type: str,
        stream_id: bytes,
        source_is_obp: bool,
    ) -> VoiceIngress | None:
        mode = "OPENBRIDGE" if source_is_obp else self._config.get("SYSTEMS", {}).get(system_name, {}).get("MODE", "")
        return build_voice_ingress(
            source_system=system_name,
            system_mode=mode if isinstance(mode, str) else "",
            peer_id=peer_id,
            rf_src=rf_src,
            dst_id=dst_id,
            slot=slot,
            call_type=call_type,
            stream_id=stream_id,
        )

    def _voice_relay_tables_with_active_source(
        self,
        system_name: str,
        bridge_match_slot: int,
        dst_int: int,
    ) -> tuple[str, ...]:
        tables, _ = self._voice_forward_plan(
            system_name=system_name,
            peer_id=b"",
            rf_src=b"",
            dst_id=b"\x00\x00\x00",
            slot=bridge_match_slot,
            call_type="group",
            stream_id=b"",
            source_is_obp=False,
            bridge_match_slot=bridge_match_slot,
            dst_int=dst_int,
            ingress_required=False,
        )
        return tables

    def _voice_forward_plan(
        self,
        *,
        system_name: str,
        peer_id: bytes,
        rf_src: bytes,
        dst_id: bytes,
        slot: int,
        call_type: str,
        stream_id: bytes,
        source_is_obp: bool,
        bridge_match_slot: int,
        dst_int: int,
        ingress_required: bool = True,
    ) -> tuple[tuple[str, ...], tuple[ForwardLeg, ...]]:
        """Return bridge tables and resolved forward legs from the subscription store."""
        router = self._subscription_router_instance()
        tables = router.relay_tables_with_active_source(system_name, bridge_match_slot, dst_int)
        if not ingress_required:
            return tables, ()
        ingress = self._build_dmrd_voice_ingress(
            system_name=system_name,
            peer_id=peer_id,
            rf_src=rf_src,
            dst_id=dst_id,
            slot=slot,
            call_type=call_type,
            stream_id=stream_id,
            source_is_obp=source_is_obp,
        )
        if ingress is None:
            return tables, ()
        return tables, router.resolve(ingress)
