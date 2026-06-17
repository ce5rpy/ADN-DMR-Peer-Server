# ADN DMR Peer Server - tests application dynamic tg persist
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

"""Persist SINGLE=1 absolute expiry to MariaDB."""

from __future__ import annotations

from adn_server.application.dynamic_tg_use_cases import DynamicTgUseCases
from adn_server.application.routing.helpers import register_peer_ua_session
from adn_server.domain.dynamic_tg import DynamicTgEntry
from tests.application.test_peer_single_downlink import _peer_id, _sys_cfg


class _CaptureStore:
    def __init__(self) -> None:
        self.replaced: list[DynamicTgEntry] = []

    def upsert(self, entry: DynamicTgEntry) -> None:
        pass

    def replace_single_slot(self, entry: DynamicTgEntry) -> None:
        self.replaced.append(entry)

    def delete_peer_slot(self, int_id: int, system_name: str, slot: int) -> None:
        pass

    def delete_peer(self, int_id: int, system_name: str) -> None:
        pass

    def load_peer(self, int_id: int, system_name: str):
        return []

    def purge_expired(self, now: float) -> None:
        pass


def test_persist_after_register_stores_absolute_expires_from_memory() -> None:
    peer_id = _peer_id()
    sys_cfg = _sys_cfg()
    peer = {"OPTIONS": b"TS2=730,7305;SINGLE=1;TIMER=60;"}
    now = 1_700_000_000.0
    register_peer_ua_session(peer, peer_id, 2, 7304, sys_cfg, now=now)
    store = _CaptureStore()
    uc = DynamicTgUseCases(store)
    uc.persist_after_register(
        peer, peer_id, 2, 7304, sys_cfg, system_name="MASTER-A",
    )
    assert len(store.replaced) == 1
    entry = store.replaced[0]
    assert entry.expires_at == now + 60.0 * 60.0
    assert entry.single_mode is True
