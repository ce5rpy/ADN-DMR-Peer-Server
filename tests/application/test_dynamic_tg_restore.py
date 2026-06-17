# ADN DMR Peer Server - tests application dynamic tg restore
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

"""Restore persisted dynamic TG rows into in-memory UA stores."""

from __future__ import annotations

import pytest

from adn_server.application.routing.helpers import (
    peer_should_receive_group_voice,
    purge_expired_peer_ua_sessions,
    restore_peer_ua_entries_to_memory,
)
from adn_server.domain.dynamic_tg import DynamicTgEntry
from tests.application.test_peer_single_downlink import _peer_id, _sys_cfg


def test_restore_single_mode_respects_expiry() -> None:
    peer_id = _peer_id()
    sys_cfg = _sys_cfg()
    now = 1_000_000.0
    entries = [
        DynamicTgEntry(
            int_id=730039101,
            system_name="MASTER-A",
            slot=2,
            tgid=7305,
            single_mode=True,
            expires_at=now + 300.0,
            updated_at=now,
        ),
        DynamicTgEntry(
            int_id=730039101,
            system_name="MASTER-A",
            slot=2,
            tgid=730,
            single_mode=True,
            expires_at=now - 1.0,
            updated_at=now - 60.0,
        ),
    ]
    restored = restore_peer_ua_entries_to_memory(sys_cfg, peer_id, entries, now=now + 10)
    assert restored == [7305]
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    assert peer_should_receive_group_voice(
        peer, 2, 7305, peer_id=peer_id, connected_count=2, sys_cfg=sys_cfg, now=now + 20
    )
    assert not peer_should_receive_group_voice(
        peer, 2, 730, peer_id=peer_id, connected_count=2, sys_cfg=sys_cfg, now=now + 20
    )


def test_restore_single_zero_multi_dynamic() -> None:
    peer_id = _peer_id()
    sys_cfg = _sys_cfg()
    now = 1_000_000.0
    entries = [
        DynamicTgEntry(
            int_id=730039101,
            system_name="MASTER-A",
            slot=2,
            tgid=7304,
            single_mode=False,
            expires_at=None,
            updated_at=now,
        ),
        DynamicTgEntry(
            int_id=730039101,
            system_name="MASTER-A",
            slot=2,
            tgid=7306,
            single_mode=False,
            expires_at=None,
            updated_at=now,
        ),
    ]
    restored = restore_peer_ua_entries_to_memory(sys_cfg, peer_id, entries, now=now)
    assert sorted(restored) == [7304, 7306]
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=0;"}
    assert peer_should_receive_group_voice(
        peer, 2, 7304, peer_id=peer_id, connected_count=2, sys_cfg=sys_cfg, now=now + 10
    )
    assert peer_should_receive_group_voice(
        peer, 2, 7306, peer_id=peer_id, connected_count=2, sys_cfg=sys_cfg, now=now + 10
    )


def test_restore_single_preserves_absolute_expires_timestamp() -> None:
    """SINGLE=1: reconnect restores the same wall-clock expiry, not a fresh TIMER."""
    peer_id = _peer_id()
    sys_cfg: dict = {}
    activated_at = 1_700_000_000.0
    expires_at = activated_at + 60.0 * 60.0  # TIMER=60 at activation
    reconnect_at = activated_at + 34.0 * 60.0  # 26 minutes remaining
    entries = [
        DynamicTgEntry(
            int_id=730039101,
            system_name="MASTER-A",
            slot=2,
            tgid=7304,
            single_mode=True,
            expires_at=expires_at,
            updated_at=activated_at,
        ),
    ]
    restore_peer_ua_entries_to_memory(sys_cfg, peer_id, entries, now=reconnect_at)
    pk_sessions = sys_cfg["_PEER_UA_SESSIONS"]
    per_peer = next(iter(pk_sessions.values()))
    assert per_peer[2]["expires"] == expires_at
    assert per_peer[2]["expires"] - reconnect_at == pytest.approx(26.0 * 60.0, rel=0.01)


def test_purge_expired_peer_ua_sessions() -> None:
    peer_id = _peer_id()
    sys_cfg = _sys_cfg()
    now = 1_000_000.0
    entries = [
        DynamicTgEntry(
            int_id=730039101,
            system_name="MASTER-A",
            slot=2,
            tgid=7304,
            single_mode=True,
            expires_at=now + 60.0,
            updated_at=now,
        ),
    ]
    restore_peer_ua_entries_to_memory(sys_cfg, peer_id, entries, now=now)
    purge_expired_peer_ua_sessions(sys_cfg, now=now + 120)
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=5;"}
    assert not peer_should_receive_group_voice(
        peer, 2, 7304, peer_id=peer_id, connected_count=2, sys_cfg=sys_cfg, now=now + 130
    )
