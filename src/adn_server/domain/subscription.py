"""Subscription model: logical TG channels and per-system participation (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .value_objects import Slot, TgId


class SubscriptionRole(str, Enum):
    """How a system participates in an audio channel."""

    SINK = "sink"
    SOURCE = "source"
    PASSIVE_STAT = "passive_stat"
    ECHO = "echo"


class ActivationPolicy(str, Enum):
    """What may activate this subscription (separate from session state)."""

    USER_ACTIVATED = "user_activated"
    STATIC = "static"
    INBAND = "inband"
    OPENBRIDGE_STAT = "openbridge_stat"


class SubscriptionPhase(str, Enum):
    """Runtime session phase for a subscription leg."""

    IDLE = "idle"
    ACTIVE = "active"
    HANGTIME = "hangtime"


@dataclass(frozen=True, slots=True)
class SystemId:
    """Enabled system name (legacy BRIDGES row ``SYSTEM``)."""

    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AudioChannel:
    """Logical talkgroup channel: ``(tgid, slot)``."""

    tgid: TgId
    slot: Slot


@dataclass(frozen=True, slots=True)
class SubscriptionId:
    """Stable key for one system leg on a channel."""

    channel: AudioChannel
    system: SystemId


@dataclass(slots=True)
class SubscriptionState:
    """Mutable session state (legacy ACTIVE / TIMER / hangtime)."""

    phase: SubscriptionPhase = SubscriptionPhase.IDLE
    timer_expires_at: float | None = None


@dataclass(slots=True)
class InbandTriggers:
    """Legacy BRIDGES row ON / OFF / RESET trigger lists (VTERM in-band rules)."""

    on: tuple[bytes, ...] = ()
    off: tuple[bytes, ...] = ()
    reset: tuple[bytes, ...] = ()


@dataclass(slots=True)
class Subscription:
    """One system participating in a channel with LC rewrite and activation rules."""

    channel: AudioChannel
    system: SystemId
    target_tgid: TgId
    role: SubscriptionRole
    policy: ActivationPolicy
    state: SubscriptionState
    relay_table_key: str | None = None
    timeout_seconds: float | None = None
    triggers: InbandTriggers = field(default_factory=InbandTriggers)

    @property
    def subscription_id(self) -> SubscriptionId:
        return SubscriptionId(channel=self.channel, system=self.system)

    def is_active(self) -> bool:
        return self.state.phase == SubscriptionPhase.ACTIVE

    def table_key(self) -> str:
        if self.relay_table_key is not None:
            return self.relay_table_key
        return str(self.channel.tgid.value)
