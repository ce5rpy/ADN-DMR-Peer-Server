# ADN DMR Peer Server - application subscription router
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

"""Resolve voice ingress to forward legs using the subscription store."""

from __future__ import annotations

from adn_server.application.ports import SubscriptionStore
from adn_server.domain.voice_routing import ForwardLeg, VoiceIngress


class SubscriptionRouter:
    """Pure router: no Twisted, no BRIDGES dict mutation (legacy parity for forward targets)."""

    def __init__(self, store: SubscriptionStore) -> None:
        self._store = store

    def resolve(self, ingress: VoiceIngress) -> tuple[ForwardLeg, ...]:
        """Return active forward legs when the source has an ACTIVE row on the dst TG (legacy to_target)."""
        match_slot = ingress.bridge_match_slot
        dst_tgid = ingress.dst_tgid.value
        tables = self.relay_tables_with_active_source(
            ingress.source_system,
            match_slot,
            dst_tgid,
        )
        if not tables:
            return ()

        legs: list[ForwardLeg] = []
        seen_obp: set[tuple[str, int]] = set()
        for table_key in tables:
            for sub in self._store.legs_in_table(table_key):
                if sub.system.value == ingress.source_system:
                    continue
                if not sub.is_active():
                    continue
                if ingress.source_is_obp:
                    obp_key = (sub.system.value, int(sub.channel.slot))
                    if obp_key in seen_obp:
                        continue
                    seen_obp.add(obp_key)
                legs.append(
                    ForwardLeg(
                        target_system=sub.system.value,
                        slot=sub.channel.slot,
                        target_tgid=sub.target_tgid,
                    )
                )
        return tuple(legs)

    def relay_tables_with_active_source(self, system: str, slot: int, dst_tgid: int) -> tuple[str, ...]:
        """Mirror legacy ``relay_tables_with_active_source`` on subscription rows."""
        return self._store.relay_tables_with_active_source(system, slot, dst_tgid)
