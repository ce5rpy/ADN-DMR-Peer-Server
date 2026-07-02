# ADN DMR Peer Server - infrastructure proxy null self service
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

"""No-op self-service store when ``SELF_SERVICE.USE_SELFSERVICE`` is false."""

from __future__ import annotations

from typing import Any

from adn_server.application.ports import ProxySelfServiceStore


class NullProxySelfServiceStore(ProxySelfServiceStore):
    """Disabled self-service: all methods are no-ops."""

    def test_db(self) -> Any:
        from twisted.internet.defer import succeed

        return succeed(True)

    def ins_conf(
        self,
        int_id: int,
        peer_id_bytes: bytes,
        callsign: str,
        host: str,
        mode: str,
    ) -> None:
        pass

    def updt_tbl(
        self,
        action: str,
        peer_id_bytes: bytes,
        *,
        psswd: str | None = None,
    ) -> None:
        pass

    def slct_opt(self, peer_id_bytes: bytes) -> Any:
        from twisted.internet.defer import succeed

        return succeed([])

    def slct_db(self) -> Any:
        from twisted.internet.defer import succeed

        return succeed([])

    def updt_lstseen(self, dmrid_list: list[tuple[bytes, ...]]) -> None:
        pass

    def reconcile_logged_in(self, connected_peer_ids: list[bytes]) -> Any:
        from twisted.internet.defer import succeed

        return succeed(None)
