# ADN DMR Peer Server - domain voice routing
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
    call_type: str = "group"
    stream_id: int | None = None
    peer_id: DmrId | None = None
    src_id: DmrId | None = None

    @property
    def bridge_match_slot(self) -> int:
        """Slot used for BRIDGES source lookup (legacy: OBP always TS1)."""
        return 1 if self.source_is_obp else int(self.slot)


@dataclass(frozen=True, slots=True)
class ForwardLeg:
    """One outbound leg: forward ingress audio to ``target_system`` on ``slot`` with LC rewrite."""

    target_system: str
    slot: Slot
    target_tgid: TgId
