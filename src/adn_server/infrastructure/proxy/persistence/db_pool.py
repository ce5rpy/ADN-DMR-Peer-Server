"""Twisted adbapi MySQL pool for proxy self-service (legacy adn-proxy parity)."""

from __future__ import annotations

import logging

from twisted.enterprise import adbapi
from twisted.internet.defer import inlineCallbacks, returnValue

logger = logging.getLogger(__name__)


def create_pool(
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


@inlineCallbacks
def test_db(pool: adbapi.ConnectionPool) -> bool:
    """Verify DB connectivity. Returns True on success."""
    try:
        res = yield pool.runQuery("SELECT 1")
        if res:
            logger.info("(SELF_SERVICE) Database connection test: OK")
        returnValue(True)
    except Exception as err:
        logger.error("(SELF_SERVICE) Database connection error: %s", err)
        returnValue(False)
