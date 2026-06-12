"""Adaptive debounce for CONFIG_SND pushes during mass peer login."""

from __future__ import annotations

import time
from collections import deque

# Normal peer connect/disconnect: near-realtime monitor update.
CONFIG_PUSH_DEBOUNCE_NORMAL_SEC = 0.3
# Many peers logging in at once: coalesce harder (monitor need not be instant).
CONFIG_PUSH_DEBOUNCE_BURST_SEC = 2.0
CONFIG_PUSH_BURST_WINDOW_SEC = 10.0
CONFIG_PUSH_BURST_MIN_CONNECTS = 5


class ConfigPushThrottle:
    """Widen CONFIG_SND debounce when peer connect rate is high."""

    def __init__(self) -> None:
        self._connect_times: deque[float] = deque()

    def note_peer_connected(self, *, now: float | None = None) -> None:
        """Record a peer reaching CONNECTION=YES (MASTER login)."""
        t = time.time() if now is None else now
        self._connect_times.append(t)
        self._prune(t)

    def debounce_seconds(self, *, now: float | None = None) -> float:
        t = time.time() if now is None else now
        self._prune(t)
        if len(self._connect_times) >= CONFIG_PUSH_BURST_MIN_CONNECTS:
            return CONFIG_PUSH_DEBOUNCE_BURST_SEC
        return CONFIG_PUSH_DEBOUNCE_NORMAL_SEC

    def _prune(self, now: float) -> None:
        cutoff = now - CONFIG_PUSH_BURST_WINDOW_SEC
        while self._connect_times and self._connect_times[0] < cutoff:
            self._connect_times.popleft()
