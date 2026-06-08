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
        match_slot: int = 1 if ingress.source_is_obp else int(ingress.slot)
        dst_tgid = ingress.dst_tgid.value
        tables = self.bridge_tables_with_active_source(
            ingress.source_system,
            match_slot,
            dst_tgid,
        )
        if not tables:
            return ()

        legs: list[ForwardLeg] = []
        seen_obp: set[tuple[str, int]] = set()
        for table_key in tables:
            for sub in self._store.snapshot():
                if sub.table_key() != table_key:
                    continue
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

    def bridge_tables_with_active_source(self, system: str, slot: int, dst_tgid: int) -> tuple[str, ...]:
        """Mirror ``BridgeRouter.bridge_tables_with_active_source`` on subscription rows."""
        tables: list[str] = []
        seen: set[str] = set()
        for sub in self._store.snapshot():
            if sub.system.value != system:
                continue
            if int(sub.channel.slot) != int(slot):
                continue
            if not sub.is_active():
                continue
            if int(sub.target_tgid) != int(dst_tgid):
                continue
            key = sub.table_key()
            if key not in seen:
                seen.add(key)
                tables.append(key)
        return tuple(sorted(tables))
