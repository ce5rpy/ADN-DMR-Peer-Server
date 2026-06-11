"""Store-native bridge_debug_loop."""

from __future__ import annotations

import logging
from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.bridges_export import _legacy_to_type
from adn_server.domain import bytes_3
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

logger = logging.getLogger(__name__)

_PROHIBITED_TABLE_KEYS = tuple(str(b) for b in range(10)) + tuple(f"#{b}" for b in range(10))


def apply_bridge_debug_store(
    store: SubscriptionStore,
    systems_cfg: dict[str, Any],
    now: float,
) -> None:
    """Remove invalid bridge keys and fix >1 active dial (#) bridge per MASTER."""
    for key in _PROHIBITED_TABLE_KEYS:
        for sub in [s for s in store.snapshot() if s.table_key() == key]:
            store.remove(sub.subscription_id)

    statroll = sum(1 for sub in store.snapshot() if _legacy_to_type(sub) == "STAT")

    for system, sys_cfg in systems_cfg.items():
        bridgeroll = 0
        dialroll = 0
        activeroll = 0
        for sub in store.snapshot():
            if sub.system.value != system:
                continue
            bridgeroll += 1
            if sub.is_active():
                if sub.table_key().startswith("#"):
                    dialroll += 1
                    activeroll += 1
                else:
                    activeroll += 1
        if bridgeroll:
            logger.debug(
                "(BRIDGEDEBUG) system %s has %s bridges of which %s are in an ACTIVE state",
                system,
                bridgeroll,
                activeroll,
            )
        if dialroll > 1 and sys_cfg.get("MODE") == "MASTER":
            logger.warning(
                "(BRIDGEDEBUG) system %s has more than one active dial bridge (%s) - fixing",
                system,
                dialroll,
            )
            _fix_duplicate_dial_bridges(store, system, sys_cfg, now)

    logger.info("(BRIDGEDEBUG) The server currently has %s STATic bridges", statroll)


def _fix_duplicate_dial_bridges(
    store: SubscriptionStore,
    system: str,
    sys_cfg: dict[str, Any],
    now: float,
) -> None:
    times: dict[float, str] = {}
    for sub in store.snapshot():
        if sub.system.value != system or not sub.is_active():
            continue
        bridge_key = sub.table_key()
        if not bridge_key.startswith("#"):
            continue
        timer = sub.state.timer_expires_at
        if isinstance(timer, (int, float)):
            times[float(timer)] = bridge_key

    _tmout = float(sys_cfg.get("DEFAULT_UA_TIMER", 10))
    timeout_sec = _tmout * 60.0
    system_id = SystemId(system)

    for bridge_key in set(times.values()):
        logger.warning("(BRIDGEDEBUG) deactivating system: %s for bridge: %s", system, bridge_key)
        try:
            setbridge = int(bridge_key[1:]) if bridge_key.startswith("#") else int(bridge_key)
        except ValueError:
            setbridge = 9
        on_trigger = bytes_3(setbridge)

        for sub in list(store.snapshot()):
            if sub.system != system_id or sub.table_key() != bridge_key:
                continue
            if int(sub.channel.slot) != 2:
                continue
            store.remove(sub.subscription_id)
            store.upsert(
                Subscription(
                    channel=AudioChannel(tgid=TgId(9), slot=2),
                    system=system_id,
                    target_tgid=TgId(9),
                    role=SubscriptionRole.SINK,
                    policy=ActivationPolicy.INBAND,
                    state=SubscriptionState(
                        phase=SubscriptionPhase.IDLE,
                        timer_expires_at=now + timeout_sec,
                    ),
                    bridge_key=bridge_key,
                    timeout_seconds=timeout_sec,
                    triggers=InbandTriggers(on=(on_trigger,), off=(), reset=()),
                )
            )
