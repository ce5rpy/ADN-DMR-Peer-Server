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
