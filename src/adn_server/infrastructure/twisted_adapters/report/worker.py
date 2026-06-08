"""Twisted LoopingCall worker that drains the bounded report queue."""

from __future__ import annotations

import logging
from typing import Any, Callable

from twisted.internet import task

from adn_server.application.report.queue import BoundedReportQueue
from adn_server.application.ports import ReportSender

logger = logging.getLogger(__name__)

DEFAULT_DRAIN_INTERVAL_SEC = 0.05


def start_report_queue_worker(
    queue: BoundedReportQueue,
    sender: ReportSender,
    *,
    interval_sec: float = DEFAULT_DRAIN_INTERVAL_SEC,
    on_errback: Callable[[Any], None] | None = None,
) -> task.LoopingCall:
    """Start periodic drain of ``queue`` into ``sender`` (synchronous TCP send on reactor)."""

    def _drain() -> None:
        try:
            queue.drain(sender)
        except Exception as e:
            logger.warning("(REPORT) queue drain failed: %s", e)

    loop = task.LoopingCall(_drain)
    deferred = loop.start(interval_sec, now=False)
    if on_errback is not None:
        deferred.addErrback(on_errback)
    logger.info(
        "(REPORT) queue worker started interval=%.3fs max_events=%s drain_per_tick=%s",
        interval_sec,
        queue.max_events,
        queue.max_drain_per_tick,
    )
    return loop
