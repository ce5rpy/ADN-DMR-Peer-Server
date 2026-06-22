# ADN DMR Peer Server - tests domain ua timer
#
# Copyright (C) 2026  Rodrigo Pérez, CE5RPY <ce5rpy@qmd.cl>

from __future__ import annotations

from adn_server.domain.ua_timer import (
    UA_TIMER_INFINITE_MINUTES,
    normalize_ua_timer_minutes,
    ua_timer_is_infinite,
)


def test_timer_zero_maps_to_legacy_infinite_sentinel() -> None:
    assert normalize_ua_timer_minutes(0, default_minutes=10) == UA_TIMER_INFINITE_MINUTES
    assert ua_timer_is_infinite(UA_TIMER_INFINITE_MINUTES)


def test_ua_session_never_expires_sentinel() -> None:
    from adn_server.domain.ua_timer import UA_SESSION_NEVER_EXPIRES_AT, ua_session_never_expires

    assert ua_session_never_expires(UA_SESSION_NEVER_EXPIRES_AT)
    assert not ua_session_never_expires(1_000_000.0)


def test_positive_timer_unchanged() -> None:
    assert normalize_ua_timer_minutes(15, default_minutes=10) == 15.0
