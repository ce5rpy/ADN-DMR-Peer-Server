"""Resolve voice ingress to forward legs using the subscription store."""

from __future__ import annotations

from adn_server.application.ports import SubscriptionStore
from adn_server.domain.subscription import AudioChannel, SubscriptionPhase
from adn_server.domain.voice_routing import ForwardLeg, VoiceIngress


class SubscriptionRouter:
    """Pure router: no Twisted, no BRIDGES dict mutation (legacy parity for forward targets)."""

    def __init__(self, store: SubscriptionStore) -> None:
        self._store = store

    def resolve(self, ingress: VoiceIngress) -> tuple[ForwardLeg, ...]:
        """Return active forward legs when the source subscription is ACTIVE on the dst channel."""
        table_key = str(ingress.dst_tgid.value)
        match_slot: int = 1 if ingress.source_is_obp else int(ingress.slot)
        source_channel = AudioChannel(tgid=ingress.dst_tgid, slot=match_slot)  # type: ignore[arg-type]

        if not self._source_is_active(ingress.source_system, source_channel):
            return ()

        legs: list[ForwardLeg] = []
        for sub in self._store.snapshot():
            if sub.table_key() != table_key:
                continue
            if sub.system.value == ingress.source_system:
                continue
            if not sub.is_active():
                continue
            legs.append(
                ForwardLeg(
                    target_system=sub.system.value,
                    slot=sub.channel.slot,
                    target_tgid=sub.target_tgid,
                )
            )
        return tuple(legs)

    def _source_is_active(self, source_system: str, channel: AudioChannel) -> bool:
        for sub in self._store.list_by_channel(channel):
            if sub.system.value != source_system:
                continue
            return sub.state.phase == SubscriptionPhase.ACTIVE
        return False
