"""Store-native bridge_reset_loop helpers (P2-015)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.application.subscription.bridges_export import _legacy_to_type
from adn_server.domain import bytes_3
from adn_server.domain.subscription import (
    ActivationPolicy,
    AudioChannel,
    InbandTriggers,
    Subscription,
    SubscriptionId,
    SubscriptionPhase,
    SubscriptionRole,
    SubscriptionState,
    SystemId,
    TgId,
)

logger = logging.getLogger(__name__)

_PROHIBITED_STATIC_TGS = (0, 1, 2, 3, 4, 5, 9, 9990, 9991, 9992, 9993, 9994, 9995, 9996, 9997, 9998, 9999)


def deactivate_system_legs_store(
    store: SubscriptionStore,
    system_name: str,
    now: float,
) -> None:
    """Mirror ``remove_bridge_system``: deactivate all legs for one system."""
    system_id = SystemId(system_name)
    for sub in list(store.list_by_system(system_id)):
        timeout = sub.timeout_seconds
        if timeout is None or isinstance(timeout, str):
            timeout = 600.0
        timeout_sec = float(timeout)
        target_b = bytes_3(int(sub.target_tgid))
        sub.state.phase = SubscriptionPhase.IDLE
        sub.role = SubscriptionRole.SINK
        sub.policy = ActivationPolicy.INBAND
        sub.state.timer_expires_at = now + timeout_sec
        sub.triggers = InbandTriggers(on=(target_b,), off=(), reset=())
        store.upsert(sub)


def restore_prohibited_static_legs_store(
    store: SubscriptionStore,
    system_name: str,
    sys_cfg: dict[str, Any],
    acl_check: Callable[[bytes, Any], bool],
    now: float,
) -> None:
    """Restore service (ECHO/NONE) legs for prohibited static TGs after BRIDGERESET."""
    if sys_cfg.get("MODE") != "MASTER" or not sys_cfg.get("ENABLED", True):
        return

    system_id = SystemId(system_name)
    timeout_sec = (1.0 / 6.0) * 60.0

    for ts, static_key, acl_key in (
        (1, "TS1_STATIC", "TG1_ACL"),
        (2, "TS2_STATIC", "TG2_ACL"),
    ):
        for tg_s in str(sys_cfg.get(static_key) or "").split(","):
            tg_s = tg_s.strip()
            if not tg_s:
                continue
            try:
                tg = int(tg_s)
            except ValueError:
                continue
            if tg not in _PROHIBITED_STATIC_TGS:
                continue
            if sys_cfg.get("USE_ACL") and not acl_check(bytes_3(tg), sys_cfg.get(acl_key, (True, []))):
                continue

            channel = AudioChannel(tgid=TgId(tg), slot=ts)
            sub_id = SubscriptionId(channel=channel, system=system_id)
            existing = store.get(sub_id)
            if existing is not None and existing.is_active() and _legacy_to_type(existing) == "NONE":
                continue

            service_leg = Subscription(
                channel=channel,
                system=system_id,
                target_tgid=TgId(tg),
                role=SubscriptionRole.ECHO,
                policy=ActivationPolicy.INBAND,
                state=SubscriptionState(
                    phase=SubscriptionPhase.ACTIVE,
                    timer_expires_at=now + timeout_sec,
                ),
                timeout_seconds=timeout_sec,
                triggers=InbandTriggers(),
            )
            if existing is not None:
                store.remove(sub_id)
            store.upsert(service_leg)
            action = "Restored" if existing is not None else "Re-added"
            logger.info(
                "(ROUTER) %s service bridge leg: %s bridge %s TS %s",
                action,
                system_name,
                tg,
                ts,
            )
