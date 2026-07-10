# ADN DMR Peer Server - tests infrastructure dynamic tg repository
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

"""DynamicTgStore SQL operations (mock pool)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from twisted.internet.defer import succeed

from adn_server.domain.dynamic_tg import DynamicTgEntry
from adn_server.infrastructure.persistence.dynamic_tg_repository import MysqlDynamicTgRepository


def _entry(**kwargs) -> DynamicTgEntry:
    defaults = dict(
        int_id=730039101,
        system_name="MASTER-A",
        slot=2,
        tgid=7305,
        single_mode=True,
        expires_at=9_999_999.0,
        updated_at=1_000_000.0,
    )
    defaults.update(kwargs)
    return DynamicTgEntry(**defaults)


@pytest.fixture
def repo() -> MysqlDynamicTgRepository:
    pool = MagicMock()
    pool.runOperation.return_value = succeed(None)
    pool.runQuery.return_value = succeed([])
    return MysqlDynamicTgRepository(pool)


def test_upsert_issues_insert(repo: MysqlDynamicTgRepository) -> None:
    repo.upsert(_entry())
    sql, args = repo._pool.runOperation.call_args[0]  # noqa: SLF001
    assert "INSERT INTO peer_dynamic_tgs" in sql
    assert args[0] == 730039101
    assert args[3] == 7305


def test_replace_single_slot_deletes_then_upserts(repo: MysqlDynamicTgRepository) -> None:
    repo.replace_single_slot(_entry())
    delete_sql = repo._pool.runOperation.call_args_list[0][0][0]  # noqa: SLF001
    assert "DELETE FROM peer_dynamic_tgs" in delete_sql


def test_delete_peer_slot(repo: MysqlDynamicTgRepository) -> None:
    repo.delete_peer_slot(730039101, "MASTER-A", 2)
    sql, args = repo._pool.runOperation.call_args[0]  # noqa: SLF001
    assert "DELETE FROM peer_dynamic_tgs" in sql
    assert args == (730039101, "MASTER-A", 2)


def test_delete_peer(repo: MysqlDynamicTgRepository) -> None:
    repo.delete_peer(730039101, "MASTER-A")
    sql, args = repo._pool.runOperation.call_args[0]  # noqa: SLF001
    assert "DELETE FROM peer_dynamic_tgs" in sql
    assert "slot" not in sql
    assert args == (730039101, "MASTER-A")


def test_purge_expired(repo: MysqlDynamicTgRepository) -> None:
    repo.purge_expired(1_000_000.0)
    sql, args = repo._pool.runOperation.call_args[0]  # noqa: SLF001
    assert "expires_at <= %s" in sql
    assert args == (1_000_000,)


def test_select_need_reload(repo: MysqlDynamicTgRepository) -> None:
    repo._pool.runQuery.return_value = succeed([(730039101, "MASTER-A")])  # noqa: SLF001
    result: list = []
    d = repo.select_need_reload()
    d.addCallback(result.append)
    from twisted.internet import reactor

    reactor.runUntilCurrent()
    assert result[0] == [(730039101, "MASTER-A")]
    sql = repo._pool.runQuery.call_args[0][0]  # noqa: SLF001
    assert "need_reload=1" in sql


def test_load_peer_maps_rows(repo: MysqlDynamicTgRepository) -> None:
    repo._pool.runQuery.return_value = succeed(  # noqa: SLF001
        [(730039101, "MASTER-A", 2, 7304, 0, None, 1_000_000.0, 0)]
    )
    result: list = []
    d = repo.load_peer(730039101, "MASTER-A")
    d.addCallback(result.append)
    from twisted.internet import reactor

    reactor.runUntilCurrent()
    assert len(result) == 1
    assert result[0][0].tgid == 7304
    assert result[0][0].single_mode is False
