# ADN DMR Peer Server - application dynamic tg use cases
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

"""Persist/restore per-peer dynamic TGs via ``DynamicTgStore`` port (voice path non-blocking)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from adn_server.application.ports import DynamicTgStore
from adn_server.application.routing.helpers import (
    _peer_ua_session_entry,
    is_ua_session_tgid,
    peer_receives_group_tgid,
    peer_single_mode,
    purge_expired_peer_ua_sessions,
    restore_peer_ua_entries_to_memory,
)
from adn_server.domain import int_id
from adn_server.domain.dynamic_tg import DynamicTgEntry, is_persisted_dynamic_row
from adn_server.domain.value_objects import bytes_4

logger = logging.getLogger(__name__)


class DynamicTgUseCases:
    def __init__(
        self,
        store: DynamicTgStore,
        *,
        on_restored: Callable[[bytes, str, dict[str, Any], list[DynamicTgEntry], float], None]
        | None = None,
    ) -> None:
        self._store = store
        self._on_restored = on_restored

    def persist_after_register(
        self,
        peer: dict[str, Any],
        peer_id: bytes,
        slot: int,
        tgid: int,
        sys_cfg: dict[str, Any],
        *,
        system_name: str,
    ) -> None:
        """Enqueue DB write (async); memory already updated by register_peer_ua_session."""
        if not is_ua_session_tgid(int(tgid)) or peer_receives_group_tgid(peer, slot, int(tgid)):
            return
        now = time.time()
        peer_int = int_id(peer_id)
        if peer_single_mode(peer, sys_cfg):
            session = _peer_ua_session_entry(sys_cfg, peer_id, int(slot))
            if not session:
                return
            self._store.replace_single_slot(
                DynamicTgEntry(
                    int_id=peer_int,
                    system_name=system_name,
                    slot=int(slot),
                    tgid=int(tgid),
                    single_mode=True,
                    expires_at=float(session["expires"]),
                    updated_at=now,
                )
            )
        else:
            self._store.upsert(
                DynamicTgEntry(
                    int_id=peer_int,
                    system_name=system_name,
                    slot=int(slot),
                    tgid=int(tgid),
                    single_mode=False,
                    expires_at=None,
                    updated_at=now,
                )
            )

    def delete_peer_slot(self, peer_id: bytes, system_name: str, slot: int) -> None:
        self._store.delete_peer_slot(int_id(peer_id), system_name, int(slot))

    def delete_peer(self, peer_id: bytes, system_name: str) -> None:
        self._store.delete_peer(int_id(peer_id), system_name)

    def restore_peer(self, peer_id: bytes, system_name: str, sys_cfg: dict[str, Any]) -> Any:
        """Load from persistence on reconnect (RPTC); returns async handle from port."""
        now = time.time()

        def _apply(entries: list[DynamicTgEntry]) -> list[int]:
            active = [
                e for e in entries
                if is_persisted_dynamic_row(e)
                and (not e.single_mode or e.expires_at is None or float(e.expires_at) > now)
            ]
            tgids = restore_peer_ua_entries_to_memory(sys_cfg, peer_id, active, now=now)
            if self._on_restored is not None:
                self._on_restored(peer_id, system_name, sys_cfg, active, now=now)
            if tgids:
                logger.info(
                    "(DYNAMIC_TG) Restored %s TG(s) for peer %s on %s: %s",
                    len(tgids), int_id(peer_id), system_name, sorted(set(tgids)),
                )
            return tgids

        return self._store.load_peer(int_id(peer_id), system_name).addCallback(_apply)

    def purge_expired(self, config: dict[str, Any]) -> None:
        now = time.time()
        self._store.purge_expired(now)
        for sys_cfg in config.get("SYSTEMS", {}).values():
            if isinstance(sys_cfg, dict):
                purge_expired_peer_ua_sessions(sys_cfg, now=now)

    def process_reload_queue(
        self,
        *,
        try_purge: Callable[[int, str, bytes], bool],
    ) -> Any:
        """Poll ``need_reload`` rows and apply TG-4000-equivalent purge when peer is online."""

        def _on_rows(rows: list[tuple[int, str]] | None) -> None:
            for peer_int, system_name in rows or []:
                peer_id = bytes_4(peer_int)
                try:
                    if try_purge(peer_int, system_name, peer_id):
                        logger.info(
                            "(DYNAMIC_TG) Applied monitor reload for peer %s on %s",
                            peer_int,
                            system_name,
                        )
                except Exception as err:
                    logger.warning(
                        "(DYNAMIC_TG) reload for peer %s on %s failed: %s",
                        peer_int,
                        system_name,
                        err,
                    )

        return self._store.select_need_reload().addCallback(_on_rows)
