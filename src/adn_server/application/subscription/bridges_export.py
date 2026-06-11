"""One-way export: SubscriptionStore → legacy ``BRIDGES`` dict (D-08)."""

from __future__ import annotations

import time
from typing import Any

from adn_server.application.ports import SubscriptionStore
from adn_server.domain import bytes_3
from adn_server.domain.subscription import (
    ActivationPolicy,
    Subscription,
    SubscriptionPhase,
    SubscriptionRole,
)

_DEFAULT_TIMEOUT_SEC = 600.0


def subscription_to_legacy_row(sub: Subscription, *, now: float | None = None) -> dict[str, Any]:
    """Map one subscription to a legacy ``BRIDGES[table][i]`` row."""
    epoch = time.time() if now is None else now
    channel_b = bytes_3(int(sub.channel.tgid))
    target_b = bytes_3(int(sub.target_tgid))
    to_type = _legacy_to_type(sub)
    timeout = _legacy_timeout(sub, to_type)
    on_list, off_list = _legacy_on_off(sub, channel_b, to_type)
    active = sub.state.phase == SubscriptionPhase.ACTIVE
    timer = sub.state.timer_expires_at
    if timer is None:
        timer = epoch + timeout if isinstance(timeout, (int, float)) else epoch

    return {
        "SYSTEM": sub.system.value,
        "TS": sub.channel.slot,
        "TGID": target_b,
        "ACTIVE": active,
        "TIMEOUT": timeout,
        "TO_TYPE": to_type,
        "ON": on_list,
        "OFF": off_list,
        "RESET": list(sub.triggers.reset),
        "TIMER": timer,
    }


def export_bridges(
    store: SubscriptionStore,
    *,
    now: float | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build a legacy ``BRIDGES`` snapshot from the subscription store (export only)."""
    epoch = time.time() if now is None else now
    bridges: dict[str, list[dict[str, Any]]] = {}
    for sub in store.snapshot():
        key = sub.table_key()
        bridges.setdefault(key, []).append(subscription_to_legacy_row(sub, now=epoch))
    return bridges


def _legacy_to_type(sub: Subscription) -> str:
    if sub.role == SubscriptionRole.ECHO:
        return "NONE"
    if sub.role == SubscriptionRole.PASSIVE_STAT:
        return "STAT"
    if sub.policy == ActivationPolicy.STATIC and sub.state.phase == SubscriptionPhase.ACTIVE:
        return "OFF"
    return "ON"


def _legacy_timeout(sub: Subscription, to_type: str) -> float | str:
    if to_type == "STAT":
        return ""
    if sub.timeout_seconds is not None:
        return sub.timeout_seconds
    return _DEFAULT_TIMEOUT_SEC


def _legacy_on_off(
    sub: Subscription,
    channel_b: bytes,
    to_type: str,
) -> tuple[list[bytes], list[bytes]]:
    if to_type == "STAT":
        return [], []
    if to_type == "NONE":
        return [], []
    on_list = list(sub.triggers.on) if sub.triggers.on else [channel_b]
    return on_list, list(sub.triggers.off)
