# ADN DMR Peer Server - tests infrastructure mysql pool ensure
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

"""Startup ensure for peer_dynamic_tgs (server-owned migration)."""

from __future__ import annotations

from unittest.mock import MagicMock

from adn_server.infrastructure.persistence.mysql_pool import _ensure_peer_dynamic_tgs_on_cursor


def test_ensure_peer_dynamic_tgs_applies_migration_once() -> None:
    cur = MagicMock()
    cur.fetchone.side_effect = [None, (1,)]  # migration missing, then exists on re-check path
    _ensure_peer_dynamic_tgs_on_cursor(cur)
    executed = [call[0][0] for call in cur.execute.call_args_list]
    assert any("schema_migrations" in sql for sql in executed)
    assert any("peer_dynamic_tgs" in sql for sql in executed)
    assert any("INSERT IGNORE INTO schema_migrations" in sql for sql in executed)


def test_ensure_peer_dynamic_tgs_skips_when_migration_marked() -> None:
    cur = MagicMock()
    cur.fetchone.return_value = (1,)
    _ensure_peer_dynamic_tgs_on_cursor(cur)
    executed = [call[0][0] for call in cur.execute.call_args_list]
    assert any("schema_migrations" in sql for sql in executed)
    assert not any("CREATE TABLE IF NOT EXISTS peer_dynamic_tgs" in sql for sql in executed)
