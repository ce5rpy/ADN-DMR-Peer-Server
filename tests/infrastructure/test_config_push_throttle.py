# ADN DMR Peer Server - tests infrastructure config push throttle
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
