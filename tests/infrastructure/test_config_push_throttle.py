"""CONFIG_SND adaptive debounce during peer login bursts."""

from __future__ import annotations

from adn_server.infrastructure.config_push_throttle import (
    CONFIG_PUSH_BURST_MIN_CONNECTS,
    CONFIG_PUSH_DEBOUNCE_BURST_SEC,
    CONFIG_PUSH_DEBOUNCE_NORMAL_SEC,
    ConfigPushThrottle,
)


def test_normal_debounce_with_few_connects() -> None:
    throttle = ConfigPushThrottle()
    base = 1_700_000_000.0
    for i in range(CONFIG_PUSH_BURST_MIN_CONNECTS - 1):
        throttle.note_peer_connected(now=base + i)
    assert throttle.debounce_seconds(now=base + 10) == CONFIG_PUSH_DEBOUNCE_NORMAL_SEC


def test_burst_debounce_after_many_connects_in_window() -> None:
    throttle = ConfigPushThrottle()
    base = 1_700_000_000.0
    for i in range(CONFIG_PUSH_BURST_MIN_CONNECTS):
        throttle.note_peer_connected(now=base + i * 0.5)
    assert throttle.debounce_seconds(now=base + 5) == CONFIG_PUSH_DEBOUNCE_BURST_SEC


def test_burst_window_expires() -> None:
    throttle = ConfigPushThrottle()
    base = 1_700_000_000.0
    for i in range(CONFIG_PUSH_BURST_MIN_CONNECTS):
        throttle.note_peer_connected(now=base + i)
    assert throttle.debounce_seconds(now=base + 20) == CONFIG_PUSH_DEBOUNCE_NORMAL_SEC
