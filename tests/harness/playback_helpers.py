"""Helpers for PlaybackUseCases tests without a live reactor."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from tests.harness.deterministic import PacketSpec


class FakePlaybackProtocol:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.STATUS: dict[int, dict[str, Any]] = {1: {}, 2: {}}

    def send_system(self, packet: bytes) -> None:
        self.sent.append(packet)


def packet_bytes(spec: PacketSpec) -> bytes:
    return spec.data()


def install_reactor_capture() -> tuple[MagicMock, list[tuple[float, Any, tuple[Any, ...]]]]:
    """Patch reactor.callLater; returns mock and scheduled (delay, fn, args) list."""
    scheduled: list[tuple[float, Any, tuple[Any, ...]]] = []
    mock_reactor = MagicMock()

    def call_later(delay: float, fn: Any, *args: Any) -> MagicMock:
        scheduled.append((delay, fn, args))
        handle = MagicMock()
        handle.active.return_value = True
        handle.cancel = MagicMock()
        return handle

    mock_reactor.callLater = call_later
    return mock_reactor, scheduled


def run_scheduled(
    scheduled: list[tuple[float, Any, tuple[Any, ...]]],
    *,
    delay: float | None = None,
) -> None:
    pending = list(scheduled)
    scheduled.clear()
    for item_delay, fn, args in pending:
        if delay is None or item_delay == delay:
            fn(*args)


def send_playback(pb: Any, system: str, spec: PacketSpec, *, ingress_pkt_time: float | None = None) -> None:
    args = spec.decoded_hbp_args()
    kwargs: dict[str, Any] = {}
    if ingress_pkt_time is not None:
        kwargs["ingress_pkt_time"] = ingress_pkt_time
    pb.dmrd_received(
        system,
        args["peer_id"],
        args["rf_src"],
        args["dst_id"],
        args["seq"],
        args["slot"],
        args["call_type"],
        args["frame_type"],
        args["dtype_vseq"],
        args["stream_id"],
        spec.data(),
        **kwargs,
    )
