# ADN DMR Peer Server - UA dynamic TG timer sentinel
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

"""Legacy OPTIONS ``TIMER=0`` / ``DEFAULT_UA_TIMER: 0`` → no expiry (bridge_master parity)."""

from __future__ import annotations

# Minutes (~68 years); legacy ``35791394`` sentinel for “no UA timeout”.
UA_TIMER_INFINITE_MINUTES = 35_791_394.0
# Stored in ``_PEER_UA_SESSIONS`` / monitor ``UA_SESSION_EXPIRES`` when TIMER has no expiry.
UA_SESSION_NEVER_EXPIRES_AT = 0.0


def ua_timer_is_infinite(minutes: float) -> bool:
    return float(minutes) >= UA_TIMER_INFINITE_MINUTES - 1.0


def ua_session_never_expires(expires_at: float) -> bool:
    """True when a SINGLE session has no wall-clock expiry (TIMER=0 / infinite)."""
    return float(expires_at) == UA_SESSION_NEVER_EXPIRES_AT


def normalize_ua_timer_minutes(raw: float, *, default_minutes: float) -> float:
    """Map TIMER/DEFAULT_UA_TIMER; ``<= 0`` → infinite sentinel (runtime bridge expiry)."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float(default_minutes)
    if value <= 0:
        return UA_TIMER_INFINITE_MINUTES
    return value
