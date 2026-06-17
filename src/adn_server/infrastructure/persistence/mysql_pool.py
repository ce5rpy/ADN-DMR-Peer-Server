# ADN DMR Peer Server - infrastructure persistence mysql pool helpers
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

"""Shared Twisted adbapi MySQL pool helpers."""

from __future__ import annotations

import logging

from twisted.enterprise import adbapi

logger = logging.getLogger(__name__)


def create_mysql_pool(
    host: str,
    user: str,
    password: str,
    db_name: str,
    port: int,
) -> adbapi.ConnectionPool:
    """Create Twisted adbapi pool using ``MySQLdb`` (``mysqlclient`` package)."""
    return adbapi.ConnectionPool(
        "MySQLdb",
        host=host,
        user=user,
        passwd=password,
        db=db_name,
        port=port,
        charset="utf8mb4",
    )


def verify_database_sync(
    host: str,
    user: str,
    password: str,
    db_name: str,
    port: int,
) -> bool:
    """Blocking startup check: MariaDB reachable and ``peer_dynamic_tgs`` exists."""
    try:
        import MySQLdb
    except ImportError as err:
        logger.critical(
            "(DATABASE) mysqlclient required for dynamic TG persistence: %s",
            err,
        )
        return False
    try:
        conn = MySQLdb.connect(
            host=host,
            user=user,
            passwd=password,
            db=db_name,
            port=port,
            charset="utf8mb4",
        )
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM peer_dynamic_tgs LIMIT 1")
        cur.close()
        conn.close()
        logger.info("(DATABASE) peer_dynamic_tgs table: OK")
        return True
    except Exception as err:
        logger.critical(
            "(DATABASE) startup check failed: %s "
            "(configure DATABASE in adn-server.yaml and run adn-monitor db_bootstrap --update)",
            err,
        )
        return False
