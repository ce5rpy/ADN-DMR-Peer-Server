"""Hotspot proxy domain: client sessions and upstream port bindings (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientEndpoint:
    """Repeater UDP endpoint (legacy ``shost`` / ``sport``)."""

    host: str
    port: int


@dataclass(frozen=True, slots=True)
class UpstreamPortRange:
    """Fan-in UDP ports on the peer server (``PORT`` .. ``PORT+GENERATOR-1``)."""

    port_start: int
    port_count: int

    def __post_init__(self) -> None:
        if self.port_count < 1:
            raise ValueError("port_count must be >= 1")
        if self.port_start < 1:
            raise ValueError("port_start must be >= 1")

    @property
    def port_end(self) -> int:
        return self.port_start + self.port_count - 1

    def ports(self) -> tuple[int, ...]:
        return tuple(range(self.port_start, self.port_end + 1))


@dataclass(frozen=True, slots=True)
class UpstreamBinding:
    """Maps one fan-in listen port to the internal master HBP endpoint."""

    listen_port: int
    master_host: str
    system_name: str | None = None


@dataclass(slots=True)
class ClientSlot:
    """Active hotspot session (legacy ``peer_track`` entry)."""

    peer_id: bytes
    client: ClientEndpoint
    upstream_port: int

    def with_client(self, host: str, port: int) -> ClientSlot:
        return ClientSlot(
            peer_id=self.peer_id,
            client=ClientEndpoint(host=host, port=port),
            upstream_port=self.upstream_port,
        )


@dataclass(frozen=True, slots=True)
class PendingRpto:
    """Options payload queued for delivery to the master on a peer upstream port."""

    peer_id: bytes
    payload: bytes
    upstream_port: int
