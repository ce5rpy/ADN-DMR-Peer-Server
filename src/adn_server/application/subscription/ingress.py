# ADN DMR Peer Server - application subscription ingress
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

"""Build immutable ``VoiceIngress`` from DMRD receive parameters (legacy ``dmrd_received``)."""

from __future__ import annotations

from adn_server.domain import int_id
from adn_server.domain.voice_routing import VoiceIngress
from adn_server.domain.value_objects import DmrId, TgId

_BRIDGE_CALL_TYPES = frozenset({"group", "vcsbk"})


def build_voice_ingress(
    *,
    source_system: str,
    system_mode: str,
    peer_id: bytes,
    rf_src: bytes,
    dst_id: bytes,
    slot: int,
    call_type: str,
    stream_id: bytes = b"",
) -> VoiceIngress | None:
    """Map ``RoutingUseCases.dmrd_received`` args to a routable ingress, or ``None`` if not bridged."""
    if call_type not in _BRIDGE_CALL_TYPES:
        return None
    match_slot = 1 if int(slot) == 1 else 2
    return VoiceIngress(
        source_system=source_system,
        slot=match_slot,  # type: ignore[arg-type]
        dst_tgid=TgId(int_id(dst_id)),
        source_is_obp=system_mode == "OPENBRIDGE",
        call_type=call_type,
        stream_id=_stream_id(stream_id),
        peer_id=_optional_dmr_id(peer_id),
        src_id=_optional_dmr_id(rf_src),
    )


def _optional_dmr_id(raw: bytes) -> DmrId | None:
    if not raw:
        return None
    value = int_id(raw)
    if value == 0:
        return None
    return DmrId(value)


def _stream_id(raw: bytes) -> int | None:
    if not raw:
        return None
    value = int_id(raw)
    return value if value != 0 else None
