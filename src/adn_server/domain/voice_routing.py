"""Immutable voice routing messages (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass

from .value_objects import DmrId, Slot, TgId


@dataclass(frozen=True, slots=True)
class VoiceIngress:
    """Normalized group/voice packet entering the subscription router."""

    source_system: str
    slot: Slot
    dst_tgid: TgId
    source_is_obp: bool = False
    stream_id: int | None = None
    peer_id: DmrId | None = None
    src_id: DmrId | None = None


@dataclass(frozen=True, slots=True)
class ForwardLeg:
    """One outbound leg: forward ingress audio to ``target_system`` on ``slot`` with LC rewrite."""

    target_system: str
    slot: Slot
    target_tgid: TgId
