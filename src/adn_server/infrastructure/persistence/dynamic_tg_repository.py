# ADN DMR Peer Server - infrastructure persistence dynamic tg repository
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

"""MySQL ``peer_dynamic_tgs`` table adapter."""

from __future__ import annotations

import logging
import time
from typing import Any

from twisted.enterprise import adbapi
from twisted.internet.defer import inlineCallbacks, returnValue

from adn_server.application.ports import DynamicTgStore
from adn_server.domain.dynamic_tg import DynamicTgEntry

logger = logging.getLogger(__name__)


def _row_to_entry(row: tuple[Any, ...]) -> DynamicTgEntry:
    return DynamicTgEntry(
        int_id=int(row[0]),
        system_name=str(row[1]),
        slot=int(row[2]),
        tgid=int(row[3]),
        single_mode=bool(int(row[4])),
        expires_at=float(row[5]) if row[5] is not None else None,
        updated_at=float(row[6]),
    )


class MysqlDynamicTgRepository(DynamicTgStore):
    """``DynamicTgStore`` via Twisted adbapi."""

    def __init__(self, pool: adbapi.ConnectionPool) -> None:
        self._pool = pool

    def upsert(self, entry: DynamicTgEntry) -> None:
        updated = int(entry.updated_at or time.time())
        expires = int(entry.expires_at) if entry.expires_at is not None else None
        self._pool.runOperation(
            """INSERT INTO peer_dynamic_tgs
               (int_id, system_name, slot, tgid, single_mode, expires_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                 single_mode=VALUES(single_mode),
                 expires_at=VALUES(expires_at),
                 updated_at=VALUES(updated_at)""",
            (
                entry.int_id,
                entry.system_name,
                entry.slot,
                entry.tgid,
                int(entry.single_mode),
                expires,
                updated,
            ),
        ).addErrback(lambda f: logger.error("(DYNAMIC_TG) upsert: %s", f.getTraceback()))

    def replace_single_slot(self, entry: DynamicTgEntry) -> None:
        self._pool.runOperation(
            "DELETE FROM peer_dynamic_tgs WHERE int_id=%s AND system_name=%s AND slot=%s AND single_mode=1",
            (entry.int_id, entry.system_name, entry.slot),
        ).addCallback(lambda _: self.upsert(entry)).addErrback(
            lambda f: logger.error("(DYNAMIC_TG) replace_single_slot: %s", f.getTraceback())
        )

    def delete_peer_slot(self, int_id: int, system_name: str, slot: int) -> None:
        self._pool.runOperation(
            "DELETE FROM peer_dynamic_tgs WHERE int_id=%s AND system_name=%s AND slot=%s",
            (int_id, system_name, slot),
        ).addErrback(
            lambda f: logger.error("(DYNAMIC_TG) delete_peer_slot: %s", f.getTraceback())
        )

    def delete_peer(self, int_id: int, system_name: str) -> None:
        self._pool.runOperation(
            "DELETE FROM peer_dynamic_tgs WHERE int_id=%s AND system_name=%s",
            (int_id, system_name),
        ).addErrback(
            lambda f: logger.error("(DYNAMIC_TG) delete_peer: %s", f.getTraceback())
        )

    @inlineCallbacks
    def load_peer(self, int_id: int, system_name: str) -> Any:
        rows = yield self._pool.runQuery(
            """SELECT int_id, system_name, slot, tgid, single_mode, expires_at, updated_at
               FROM peer_dynamic_tgs
               WHERE int_id=%s AND system_name=%s""",
            (int_id, system_name),
        )
        returnValue([_row_to_entry(row) for row in (rows or [])])

    def purge_expired(self, now: float) -> None:
        cutoff = int(now)
        self._pool.runOperation(
            "DELETE FROM peer_dynamic_tgs WHERE single_mode=1 AND expires_at IS NOT NULL AND expires_at <= %s",
            (cutoff,),
        ).addErrback(lambda f: logger.error("(DYNAMIC_TG) purge_expired: %s", f.getTraceback()))
