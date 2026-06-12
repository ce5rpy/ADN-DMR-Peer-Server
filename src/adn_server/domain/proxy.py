# ADN DMR Peer Server - domain proxy
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

"""Hotspot proxy domain: client sessions (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientEndpoint:
    """Repeater UDP endpoint (legacy ``shost`` / ``sport``)."""

    host: str
    port: int


@dataclass(slots=True)
class ClientSlot:
    """Active hotspot session (legacy ``peer_track`` entry)."""

    peer_id: bytes
    client: ClientEndpoint
    report_slot: int | None = None

    def with_client(self, host: str, port: int) -> ClientSlot:
        return ClientSlot(
            peer_id=self.peer_id,
            client=ClientEndpoint(host=host, port=port),
            report_slot=self.report_slot,
        )


@dataclass(frozen=True, slots=True)
class PendingRpto:
    """Options payload queued for delivery to the master on a peer session."""

    peer_id: bytes
    payload: bytes
    client: ClientEndpoint


@dataclass(frozen=True, slots=True)
class SessionTeardown:
    """Hotspot session removed (timeout / reaper); I/O applied by infrastructure."""

    peer_id: bytes
    client: ClientEndpoint
