# ADN DMR Peer Server - tests infrastructure proxy self service repository
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

"""ProxySelfServiceRepository SQL for reconcile_logged_in (mock pool)."""

from __future__ import annotations

from unittest.mock import MagicMock

from twisted.internet.defer import succeed

from adn_server.infrastructure.proxy.persistence.proxy_repository import (
    ProxySelfServiceRepository,
)


def _repo() -> ProxySelfServiceRepository:
    pool = MagicMock()
    pool.runOperation.return_value = succeed(None)
    return ProxySelfServiceRepository(pool)


def test_reconcile_empty_clears_all_logged_in() -> None:
    repo = _repo()
    repo.reconcile_logged_in([])
    sql = repo._pool.runOperation.call_args[0][0]  # noqa: SLF001
    assert sql == "UPDATE Clients SET logged_in=0"


def test_reconcile_with_peers_sets_in_and_not_in() -> None:
    repo = _repo()
    peer_a = b"\x00\x70\x22\x34"
    peer_b = b"\x00\x70\x22\x35"
    repo.reconcile_logged_in([peer_a, peer_b])
    calls = repo._pool.runOperation.call_args_list  # noqa: SLF001
    assert len(calls) == 2
    set_1_sql, set_1_args = calls[0][0]
    set_0_sql, set_0_args = calls[1][0]
    assert "logged_in=1" in set_1_sql
    assert "IN (%s,%s)" in set_1_sql
    assert set_1_args == (peer_a, peer_b)
    assert "logged_in=0" in set_0_sql
    assert "NOT IN (%s,%s)" in set_0_sql
    assert set_0_args == (peer_a, peer_b)


def test_reconcile_single_peer_uses_one_placeholder() -> None:
    repo = _repo()
    peer = b"\x00\x70\x22\x34"
    repo.reconcile_logged_in([peer])
    calls = repo._pool.runOperation.call_args_list  # noqa: SLF001
    assert len(calls) == 2
    set_1_sql, set_1_args = calls[0][0]
    assert "IN (%s)" in set_1_sql
    assert set_1_args == (peer,)
