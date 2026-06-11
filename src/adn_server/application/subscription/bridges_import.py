"""Import legacy ``BRIDGES`` rows into domain subscriptions (mirror of ``bridges_export``)."""

from __future__ import annotations

from typing import Any

from adn_server.domain import int_id
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

from .trigger_bytes import trigger_bytes_tuple


def subscriptions_from_bridges(bridges: dict[str, list[dict[str, Any]]]) -> list[Subscription]:
    """Build subscriptions from a legacy ``BRIDGES`` snapshot (OPTIONS/static TG / ECHO)."""
    subs: list[Subscription] = []
    for table_key, rows in bridges.items():
        for row in rows:
            if not isinstance(row, dict):
                continue
            subs.append(_subscription_from_row(table_key, row))
    return subs


def _subscription_from_row(table_key: str, row: dict[str, Any]) -> Subscription:
    ts = int(row.get("TS") or 1)
    if table_key.startswith("#"):
        channel_tgid = int_id(row.get("TGID") or b"\x00\x00\x00")
        bridge_key = table_key
    else:
        try:
            channel_tgid = int(table_key)
        except ValueError:
            channel_tgid = int_id(row.get("TGID") or b"\x00\x00\x00")
        bridge_key = None
    to_type = str(row.get("TO_TYPE", "ON"))
    timer = row.get("TIMER")
    timer_at = float(timer) if isinstance(timer, (int, float)) else None
    timeout = row.get("TIMEOUT")
    timeout_sec = float(timeout) if isinstance(timeout, (int, float)) else None
    return Subscription(
        channel=AudioChannel(tgid=TgId(channel_tgid), slot=ts),  # type: ignore[arg-type]
        system=SystemId(str(row.get("SYSTEM", ""))),
        target_tgid=TgId(int_id(row.get("TGID") or b"\x00\x00\x00")),
        role=_role_from_to_type(to_type),
        policy=_policy_from_to_type(to_type),
        state=SubscriptionState(
            phase=SubscriptionPhase.ACTIVE if row.get("ACTIVE") else SubscriptionPhase.IDLE,
            timer_expires_at=timer_at,
        ),
        bridge_key=bridge_key,
        timeout_seconds=timeout_sec,
        triggers=InbandTriggers(
            on=trigger_bytes_tuple(row.get("ON")),
            off=trigger_bytes_tuple(row.get("OFF")),
            reset=trigger_bytes_tuple(row.get("RESET")),
        ),
    )


def _role_from_to_type(to_type: str) -> SubscriptionRole:
    if to_type == "NONE":
        return SubscriptionRole.ECHO
    if to_type == "STAT":
        return SubscriptionRole.PASSIVE_STAT
    return SubscriptionRole.SINK


def _policy_from_to_type(to_type: str) -> ActivationPolicy:
    if to_type == "STAT":
        return ActivationPolicy.OPENBRIDGE_STAT
    if to_type == "OFF":
        return ActivationPolicy.STATIC
    return ActivationPolicy.INBAND
