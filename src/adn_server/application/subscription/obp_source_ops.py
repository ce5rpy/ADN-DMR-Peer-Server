"""Store-native OBP source leg ensure (P2-015 slice 4)."""

from __future__ import annotations

from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.domain import bytes_3, int_id
from adn_server.domain.subscription import (
    ActivationPolicy,
    AudioChannel,
    InbandTriggers,
    Subscription,
    SubscriptionPhase,
    SubscriptionRole,
    SubscriptionState,
    SystemId,
    TgId,
)


def _tgid_match(entry_tgid: Any, dst_id_b: bytes, dst_int: int) -> bool:
    if entry_tgid == dst_id_b:
        return True
    try:
        return int_id(entry_tgid or b"\x00\x00\x00") == dst_int
    except (TypeError, ValueError):
        return False


def ensure_obp_source_for_tg_store(
    store: SubscriptionStore,
    system_name: str,
    bridge_key: str,
    dst_id_b: bytes,
    dst_int: int,
    now: float,
) -> None:
    """Ensure OBP has ACTIVE TS1 source row in main and #reflector tables."""
    for key in (bridge_key, "#" + bridge_key):
        if not any(sub.table_key() == key for sub in store.snapshot()):
            continue
        channel_tgid = dst_int
        patched = False
        for sub in list(store.snapshot()):
            if sub.system.value != system_name:
                continue
            if sub.table_key() != key:
                continue
            if int(sub.channel.slot) != 1:
                continue
            if not _tgid_match(bytes_3(int(sub.target_tgid.value)), dst_id_b, dst_int):
                continue
            if not sub.is_active():
                sub.state.phase = SubscriptionPhase.ACTIVE
                store.upsert(sub)
            patched = True
            break
        if not patched:
            store.upsert(
                Subscription(
                    channel=AudioChannel(tgid=TgId(channel_tgid), slot=1),  # type: ignore[arg-type]
                    system=SystemId(system_name),
                    target_tgid=TgId(dst_int),
                    role=SubscriptionRole.ECHO,
                    policy=ActivationPolicy.INBAND,
                    state=SubscriptionState(phase=SubscriptionPhase.ACTIVE, timer_expires_at=now),
                    bridge_key=key if key.startswith("#") else None,
                    timeout_seconds=None,
                    triggers=InbandTriggers(),
                )
            )
